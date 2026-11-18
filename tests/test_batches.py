"""迟到申报承接与本期发布批次测试。

业务约束：
- 闭口原月不得重开覆盖；迟到记录由开放承接期代收，量入承接期、责任溯源原属期。
- 同一输入重跑不新增批次；发布失败保留上一版可恢复；旧版可追回、可恢复。
"""
import pytest

from app.pipeline import calculate, load_sample
from app.modules.m4_increment.rules import evaluate as m4
from app.errors import DomainError
from app.batches import rules, store

PARAMS = {"periods": {"2026-08": "closed", "2026-09": "open"},
          "late_claims": [{"claim_id": "L002", "period": "2026-08", "carry_to": "2026-09"}]}
RAW = None


@pytest.fixture
def raw():
    return load_sample("late_september.csv")


def test_late_claim_carried_to_open_period(raw):
    result = calculate(raw, PARAMS)
    rows = {r["claim_id"]: r for r in result["stages"][3]["rows"]}
    late = rows["L002"]
    # 周期改写为开放承接期，原属期与依据留痕。
    assert late["period"] == "2026-09"
    assert late["origin_period"] == "2026-08"
    assert late["late_claim"] is True
    assert "2026-08" in late["carry_basis"] and "2026-09" in late["carry_basis"]
    # 量与价计入九月承接期。
    assert late["increment_qty"] == "20"
    assert result["stages"][3]["metrics"]["late_accepted"] == 1


def test_normal_claim_keeps_own_period(raw):
    result = calculate(raw, PARAMS)
    rows = {r["claim_id"]: r for r in result["stages"][-1]["rows"]}
    normal = rows["L001"]
    assert normal["period"] == "2026-09"
    assert "origin_period" not in normal


def test_carry_quarantine_keeps_lineage_balanced(raw):
    params = {"periods": {"2026-08": "closed", "2026-09": "closed"},
              "late_claims": [{"claim_id": "L002", "period": "2026-08", "carry_to": "2026-09"}]}
    result = calculate(raw, params)
    assert result["stages"][3]["metrics"]["late_quarantine"] == 1
    assert result["stages"][5]["metrics"]["balanced"] is True
    codes = {q["reason"] for q in result["stages"][-1]["cumulative_quarantine"]}
    assert "CARRY_PERIOD_NOT_OPEN" in codes


@pytest.mark.parametrize("periods,spec,code", [
    ({"2026-08": "open", "2026-09": "open"},
     {"claim_id": "L002", "period": "2026-08", "carry_to": "2026-09"}, "LATE_PERIOD_NOT_CLOSED"),
    ({"2026-08": "closed", "2026-09": "open"},
     {"claim_id": "L002", "period": "2026-07", "carry_to": "2026-09"}, "LATE_PERIOD_MISMATCH"),
    ({"2026-08": "closed", "2026-09": "closed"},
     {"claim_id": "L002", "period": "2026-08", "carry_to": "2026-09"}, "CARRY_PERIOD_NOT_OPEN"),
])
def test_late_validation_rejection(raw, periods, spec, code):
    result = calculate(raw, {"periods": periods, "late_claims": [spec]})
    assert any(q["reason"] == code for q in result["stages"][3]["quarantine"])


def test_late_claim_not_found_isolated(raw):
    params = {"periods": PARAMS["periods"],
              "late_claims": [{"claim_id": "GHOST", "period": "2026-08", "carry_to": "2026-09"}]}
    result = calculate(raw, params)
    assert any(q["reason"] == "LATE_CLAIM_NOT_FOUND" for q in result["stages"][3]["quarantine"])


def test_bad_period_status_rejected(raw):
    with pytest.raises(DomainError) as exc:
        calculate(raw, {"periods": {"2026-08": "sealed"}})
    assert exc.value.code == "BAD_PERIODS"


def test_no_late_params_keeps_legacy_behavior(raw):
    result = calculate(raw)
    rows = {r["claim_id"]: r for r in result["stages"][3]["rows"]}
    assert rows["L002"]["period"] == "2026-08"
    assert result["stages"][3]["metrics"]["late_accepted"] == 0


# ---------- 发布批次：幂等、版本、失败回滚、追回恢复 ----------

def test_prepare_idempotent_same_input(raw):
    first = rules.prepare(raw, PARAMS)
    second = rules.prepare(raw, PARAMS)
    assert first["batch_id"] == second["batch_id"]
    assert len(store.list_batches()) == 1


def test_different_input_creates_new_batch(raw):
    rules.prepare(raw, PARAMS)
    other = load_sample("dirty.csv")
    second = rules.prepare(other, {})
    assert len(store.list_batches()) == 2
    assert second["status"] == store.DRAFT and second["version"] == 0


def test_publish_creates_immutable_snapshots(raw):
    batch = rules.prepare(raw, PARAMS)
    bid = batch["batch_id"]
    store.publish(bid, 0, "2026-09-01T00:00:00+00:00")
    again = store.publish(bid, 1, "2026-09-02T00:00:00+00:00")
    assert again["version"] == 2 and again["status"] == store.PUBLISHED
    assert [v["version"] for v in again["versions"]] == [1, 2]
    # 快照内容不可变：v1 与 v2 各自留存。
    assert len(again["versions"]) == 2


def test_stale_publish_conflict(raw):
    batch = rules.prepare(raw, PARAMS)
    store.publish(batch["batch_id"], 0, "t1")
    with pytest.raises(DomainError) as exc:
        store.publish(batch["batch_id"], 0, "t2")
    assert exc.value.status == 409 and exc.value.code == "STALE_VERSION"


def test_failed_publish_rolls_back_and_keeps_previous(raw):
    import sqlite3
    batch = rules.prepare(raw, PARAMS)
    bid = batch["batch_id"]
    store.publish(bid, 0, "t1")
    with pytest.raises(sqlite3.Error):
        store.publish(bid, 1, "t2", fail=True)
    after = store.get_batch(bid)
    # 失败后版本与状态停在上一版，快照未新增，仍可再次发布或恢复。
    assert after["version"] == 1 and after["status"] == store.PUBLISHED
    assert len(after["versions"]) == 1


def test_rollback_then_restore_creates_new_version(raw):
    batch = rules.prepare(raw, PARAMS)
    bid = batch["batch_id"]
    store.publish(bid, 0, "t1")
    store.publish(bid, 1, "t2")
    rolled = store.rollback(bid, 2, "t3")
    assert rolled["status"] == store.ROLLED_BACK
    assert len(rolled["versions"]) == 2  # 快照不删除，可追回
    restored = store.restore(bid, 1, 2, "t4")
    assert restored["status"] == store.PUBLISHED and restored["version"] == 3
    assert [v["version"] for v in restored["versions"]] == [1, 2, 3]


def test_rollback_requires_published(raw):
    batch = rules.prepare(raw, PARAMS)
    with pytest.raises(DomainError) as exc:
        store.rollback(batch["batch_id"], 0, "t")
    assert exc.value.code == "NOT_PUBLISHED"


def test_restore_unknown_version_404(raw):
    batch = rules.prepare(raw, PARAMS)
    bid = batch["batch_id"]
    store.publish(bid, 0, "t1")
    with pytest.raises(DomainError) as exc:
        store.restore(bid, 99, 1, "t2")
    assert exc.value.code == "VERSION_NOT_FOUND"


def test_batch_payload_documents_each_late_claim(raw):
    batch = rules.prepare(raw, PARAMS)
    late = batch["payload"]["late_claims"][0]
    assert late["claim_id"] == "L002"
    assert late["origin_period"] == "2026-08" and late["carry_to"] == "2026-09"
    assert late["accepted"] is True and late["increment_qty"] == "20"
    totals = batch["payload"]["impact_totals"]
    assert totals["late_accepted"] == 1 and totals["late_expected"] == "1700.00"


# ---------- HTTP 接口 ----------

def test_batch_api_lifecycle(client):
    r = client.post("/api/batches", json={"sample": "late_september.csv", "parameters": PARAMS})
    assert r.status_code == 201
    bid = r.get_json()["batch_id"]
    # 幂等
    assert client.post("/api/batches",
                       json={"sample": "late_september.csv", "parameters": PARAMS}).get_json()["batch_id"] == bid
    assert len(client.get("/api/batches").get_json()["batches"]) == 1
    # 发布失败注入：500，上一版保留
    fail = client.post(f"/api/batches/{bid}/publish", json={"version": 0, "fail": True})
    assert fail.status_code == 500 and fail.get_json()["code"] == "PUBLISH_FAILED"
    assert client.get(f"/api/batches/{bid}").get_json()["version"] == 0
    # 正常发布
    ok = client.post(f"/api/batches/{bid}/publish", json={"version": 0})
    assert ok.status_code == 200 and ok.get_json()["version"] == 1
    # 追回与恢复
    assert client.post(f"/api/batches/{bid}/rollback", json={"version": 1}).status_code == 200
    rs = client.post(f"/api/batches/{bid}/restore", json={"version": 1, "target_version": 1})
    assert rs.get_json()["version"] == 2


def test_batches_page_renders(client):
    assert client.get("/batches").status_code == 200
