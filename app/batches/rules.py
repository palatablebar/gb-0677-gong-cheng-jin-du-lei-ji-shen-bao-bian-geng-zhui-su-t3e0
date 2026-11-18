"""发布批次编排：在既有 7 阶段计量结果上，叠加迟到承接说明与量影响汇总。

不重开闭口期、不覆盖原批：迟到记录的量已在 m4 阶段由开放承接期代收，
这里仅把"哪条迟到申报、由哪个开放期承接、对量的影响、依据"逐条留痕，
形成可发布的本期计量批次说明。
"""
from decimal import Decimal
from datetime import datetime, timezone

from app.manifest import digest
from app import periods as period_rules
from app.pipeline import calculate, load_sample
from app.batches import store


def prepare(raw, params, sample=None):
    """计算并幂等落草稿。批次身份仅取决于输入、参数与规则版本（不含时间戳）。"""
    params = params or {}
    result = calculate(raw, params)
    period = _batch_period(params, result)
    late_summary = _late_summary(result, params)
    payload = {"run": result, "period": period,
               "late_claims": late_summary,
               "impact_totals": _impact_totals(late_summary)}
    # 与 runs 同一稳定摘要：sha256(输入 + 参数 + 规则版本)，重跑同一输入必得同一批次。
    batch_id = "PB-" + digest(raw, params)[:20]
    created_at = datetime.now(timezone.utc).isoformat()
    return store.save_draft(batch_id, period, result["manifest"]["input_sha256"],
                            payload, created_at)


def prepare_sample(sample, params):
    return prepare(load_sample(sample), params, sample)


def _batch_period(params, result):
    status = params.get("periods")
    if status:
        opened = period_rules.open_periods(period_rules.normalize(status))
        if opened:
            return opened[0]
    periods_ = sorted({r["period"] for r in result["stages"][-1]["rows"]})
    return periods_[-1] if periods_ else "UNKNOWN"


def _late_summary(result, params):
    """逐条迟到申报：承接期、原属期、量/价影响、依据。"""
    late_specs = {str(x["claim_id"]): x for x in params.get("late_claims", [])}
    final_rows = {r["claim_id"]: r for r in result["stages"][-1]["rows"]}
    quarantine = result["stages"][-1].get("cumulative_quarantine", [])
    summary = []
    for claim_id, spec in late_specs.items():
        row = final_rows.get(claim_id)
        if row:
            summary.append({
                "claim_id": claim_id,
                "origin_period": row.get("origin_period", spec.get("period")),
                "carry_to": row["period"],
                "item": row["item"],
                "increment_qty": row["increment_qty"],
                "gross_amount": row["gross_amount"],
                "expected": row["expected"],
                "accepted": True,
                "basis": row.get("carry_basis", ""),
            })
        else:
            hit = next((q for q in quarantine
                        if q.get("claim_id") == claim_id and q.get("_late")), None)
            summary.append({
                "claim_id": claim_id,
                "origin_period": spec.get("period"),
                "carry_to": spec.get("carry_to"),
                "accepted": False,
                "reason": hit["reason"] if hit else "LATE_CLAIM_NOT_FOUND",
                "detail": hit["detail"] if hit else "迟到申报未通过承接校验，已隔离",
                "increment_qty": "0", "gross_amount": "0", "expected": "0",
            })
    return summary


def _impact_totals(late_summary):
    accepted = [x for x in late_summary if x["accepted"]]
    return {
        "late_records": len(late_summary),
        "late_accepted": len(accepted),
        "late_quarantine": len(late_summary) - len(accepted),
        # 迟到承接量并入承接期出账的合计影响（隔离记录不计量）。
        "late_gross_amount": str(sum((Decimal(x["gross_amount"]) for x in accepted), Decimal(0))),
        "late_expected": str(sum((Decimal(x["expected"]) for x in accepted), Decimal(0))),
    }
