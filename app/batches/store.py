"""发布批次的版本化存储。

两张表：
- batches：一个发布批次的当前指针（草稿/已发布/已追回），保存当前 payload。
- batch_versions：每次发布成功生成的不可变版本快照，旧版永久留存可追回。

所有写操作在单个 SQLite 事务内完成；发布失败整体回滚，上一版与批次指针
保持原样，可继续恢复。批次业务键为输入+参数+规则版本的摘要，同一输入
重跑返回同一批次，绝不新增。
"""
import json
import sqlite3

from app.config import DATA_DIR
from app.errors import DomainError

DRAFT = "草稿"
PUBLISHED = "已发布"
ROLLED_BACK = "已追回"


def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA_DIR / "records.db", timeout=20)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(
        "CREATE TABLE IF NOT EXISTS batches ("
        "id TEXT PRIMARY KEY, seq INTEGER NOT NULL, period TEXT NOT NULL, "
        "status TEXT NOT NULL, digest TEXT NOT NULL, version INTEGER NOT NULL, "
        "payload TEXT NOT NULL, created_at TEXT NOT NULL, published_at TEXT)")
    db.execute(
        "CREATE TABLE IF NOT EXISTS batch_versions ("
        "batch_id TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL, "
        "payload TEXT NOT NULL, created_at TEXT NOT NULL, "
        "PRIMARY KEY(batch_id, version))")
    db.execute(
        "CREATE TABLE IF NOT EXISTS batch_seq (name TEXT PRIMARY KEY, value INTEGER NOT NULL)")
    return db


def _next_seq(db):
    db.execute("INSERT INTO batch_seq(name,value) VALUES('batch',0) "
               "ON CONFLICT(name) DO UPDATE SET value=value+1")
    row = db.execute("SELECT value FROM batch_seq WHERE name='batch'").fetchone()
    return row[0] + 1


def save_draft(batch_id, period, digest, payload, created_at):
    """幂等创建草稿批次；同一摘要重跑复用，不新增。"""
    db = connect()
    try:
        existing = db.execute("SELECT id FROM batches WHERE id=?", (batch_id,)).fetchone()
        if existing:
            db.commit()
            return get_batch(batch_id)
        seq = _next_seq(db)
        db.execute(
            "INSERT INTO batches(id,seq,period,status,digest,version,payload,created_at,published_at) "
            "VALUES(?,?,?,?,?,?,?,?,NULL)",
            (batch_id, seq, period, DRAFT, digest, 0,
             json.dumps(payload, ensure_ascii=False), created_at))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return get_batch(batch_id)


def publish(batch_id, expected_version, created_at, fail=False):
    """发布为不可变版本。乐观版本校验，事务失败整体回滚。"""
    db = connect()
    try:
        row = db.execute(
            "SELECT status,version,payload FROM batches WHERE id=?", (batch_id,)).fetchone()
        if not row:
            raise DomainError("NOT_FOUND", "批次不存在", 404)
        status, version, payload = row
        if expected_version != version:
            raise DomainError("STALE_VERSION", "版本已更新，请刷新后再发布", 409)
        new_version = version + 1
        if fail:
            # 模拟发布落库故障：在任何写入前抛错，验证事务回滚后上一版仍可恢复。
            raise sqlite3.Error("注入的发布故障")
        db.execute("INSERT INTO batch_versions(batch_id,version,status,payload,created_at) "
                   "VALUES(?,?,?,?,?)", (batch_id, new_version, PUBLISHED, payload, created_at))
        db.execute("UPDATE batches SET status=?, version=?, published_at=? WHERE id=?",
                   (PUBLISHED, new_version, created_at, batch_id))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return get_batch(batch_id)


def rollback(batch_id, expected_version, created_at):
    """追回当前已发布版本：状态置为已追回，快照留存，不删除任何版本。"""
    db = connect()
    try:
        row = db.execute("SELECT status,version FROM batches WHERE id=?", (batch_id,)).fetchone()
        if not row:
            raise DomainError("NOT_FOUND", "批次不存在", 404)
        status, version = row
        if expected_version != version:
            raise DomainError("STALE_VERSION", "版本已更新，请刷新后再追回", 409)
        if status != PUBLISHED:
            raise DomainError("NOT_PUBLISHED", "仅已发布版本可追回", 409)
        db.execute("UPDATE batches SET status=? WHERE id=?", (ROLLED_BACK, batch_id))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return get_batch(batch_id)


def restore(batch_id, target_version, expected_version, created_at):
    """恢复到任一历史快照：以旧版 payload 生成新的当前版本，旧版不被覆盖。"""
    db = connect()
    try:
        current = db.execute("SELECT version FROM batches WHERE id=?", (batch_id,)).fetchone()
        if not current:
            raise DomainError("NOT_FOUND", "批次不存在", 404)
        if expected_version != current[0]:
            raise DomainError("STALE_VERSION", "版本已更新，请刷新后再恢复", 409)
        snapshot = db.execute(
            "SELECT payload FROM batch_versions WHERE batch_id=? AND version=?",
            (batch_id, target_version)).fetchone()
        if not snapshot:
            raise DomainError("VERSION_NOT_FOUND", "目标历史版本不存在", 404)
        new_version = current[0] + 1
        db.execute("INSERT INTO batch_versions(batch_id,version,status,payload,created_at) "
                   "VALUES(?,?,?,?,?)", (batch_id, new_version, PUBLISHED, snapshot[0], created_at))
        db.execute("UPDATE batches SET status=?, version=?, payload=?, published_at=? WHERE id=?",
                   (PUBLISHED, new_version, snapshot[0], created_at, batch_id))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return get_batch(batch_id)


def get_batch(batch_id):
    db = connect()
    try:
        row = db.execute(
            "SELECT id,seq,period,status,digest,version,payload,created_at,published_at "
            "FROM batches WHERE id=?", (batch_id,)).fetchone()
    finally:
        db.close()
    if not row:
        raise DomainError("NOT_FOUND", "批次不存在", 404)
    versions = _versions(batch_id)
    return {"batch_id": row[0], "batch_no": f"PB-{row[1]:04d}", "period": row[2],
            "status": row[3], "digest": row[4], "version": row[5],
            "payload": json.loads(row[6]), "created_at": row[7],
            "published_at": row[8], "versions": versions}


def _versions(batch_id):
    db = connect()
    try:
        rows = db.execute(
            "SELECT version,status,created_at FROM batch_versions WHERE batch_id=? ORDER BY version",
            (batch_id,)).fetchall()
    finally:
        db.close()
    return [{"version": v, "status": s, "created_at": t} for v, s, t in rows]


def list_batches():
    db = connect()
    try:
        rows = db.execute(
            "SELECT id,seq,period,status,digest,version,created_at,published_at "
            "FROM batches ORDER BY seq DESC").fetchall()
    finally:
        db.close()
    return [{"batch_id": r[0], "batch_no": f"PB-{r[1]:04d}", "period": r[2], "status": r[3],
             "digest": r[4][:12], "version": r[5], "created_at": r[6],
             "published_at": r[7]} for r in rows]
