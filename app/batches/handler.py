from datetime import datetime, timezone

from flask import Blueprint, request, jsonify

from app.errors import DomainError
from app.pipeline import load_sample
from app.batches import rules, store

bp = Blueprint("batches", __name__)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _params(payload):
    params = payload.get("parameters", {})
    if not isinstance(params, dict):
        raise DomainError("BAD_PARAMETERS", "参数需要对象")
    return params


@bp.route("/api/batches", methods=["GET", "POST"])
def collection():
    if request.method == "GET":
        return jsonify({"batches": store.list_batches()})
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise DomainError("BAD_BODY", "请求需要对象")
    params = _params(payload)
    if "csv" in payload:
        raw = payload["csv"]
        if not isinstance(raw, str):
            raise DomainError("BAD_CSV", "CSV需要文本")
        batch = rules.prepare(raw.encode(), params)
    else:
        sample = payload.get("sample", "late_september.csv")
        batch = rules.prepare_sample(sample, params)
    return jsonify(batch), 201


@bp.route("/api/batches/<batch_id>", methods=["GET"])
def detail(batch_id):
    return jsonify(store.get_batch(batch_id))


@bp.route("/api/batches/<batch_id>/publish", methods=["POST"])
def publish(batch_id):
    p = request.get_json(silent=True) or {}
    if not isinstance(p.get("version"), int):
        raise DomainError("BAD_VERSION", "请提供版本号")
    # fail=true 用于演练发布失败回滚：故障注入后上一版保持不变并可恢复。
    fail = bool(p.get("fail", False))
    return jsonify(store.publish(batch_id, p["version"], _now(), fail))


@bp.route("/api/batches/<batch_id>/rollback", methods=["POST"])
def rollback(batch_id):
    p = request.get_json(silent=True) or {}
    if not isinstance(p.get("version"), int):
        raise DomainError("BAD_VERSION", "请提供版本号")
    return jsonify(store.rollback(batch_id, p["version"], _now()))


@bp.route("/api/batches/<batch_id>/restore", methods=["POST"])
def restore(batch_id):
    p = request.get_json(silent=True) or {}
    if not isinstance(p.get("version"), int):
        raise DomainError("BAD_VERSION", "请提供当前版本号")
    if not isinstance(p.get("target_version"), int):
        raise DomainError("BAD_VERSION", "请提供要恢复的历史版本号")
    return jsonify(store.restore(batch_id, p["target_version"], p["version"], _now()))
