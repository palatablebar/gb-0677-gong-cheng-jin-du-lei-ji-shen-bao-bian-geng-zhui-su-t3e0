from app.values import number
from app.reasons import reject
from app.errors import DomainError
from app import periods


def evaluate(rows, context):
    good = []
    bad = []
    seen = set()
    late_quarantine = 0
    params = context.get("parameters", {})
    overrides = params.get("previous_revisions", {})
    period_status = periods.normalize(params["periods"]) if "periods" in params else {}
    # 迟到申报登记：claim_id -> {period（原属期）, carry_to（承接期）}
    late = {str(x["claim_id"]): x for x in params.get("late_claims", [])}
    late_found = set()

    # 先处理迟到申报承接：原地改写周期为开放承接期，并封存溯源与依据。
    rejected_indexes = set()
    for index, row in enumerate(rows):
        spec = late.get(row.get("claim_id"))
        if not spec:
            continue
        late_found.add(row["claim_id"])
        fault = periods.check_late(spec, row, period_status)
        if fault:
            # 拒收行进隔离区并从处理流剔除，避免下游重复裁决导致血缘重叠。
            bad.append(reject({**row, "_late": True}, fault[0], fault[1]))
            rejected_indexes.add(index)
            late_quarantine += 1
            continue
        target = spec["carry_to"]
        origin = row["period"]
        rows[index] = {
            **row,
            "period": target,
            "origin_period": origin,
            "late_claim": True,
            "carry_to": target,
            "carry_basis": periods.carry_basis(origin, target, row["claim_id"]),
        }

    # 迟到登记中找不到对应申报行的，隔离登记本身（保留登记依据）。
    for claim_id in late:
        if claim_id not in late_found:
            bad.append(reject({"claim_id": claim_id, "_sources": [], "_raw": [], "_late": True},
                              "LATE_CLAIM_NOT_FOUND",
                              f"迟到申报{claim_id}未在输入中找到对应申报行"))
            late_quarantine += 1

    active_rows = [row for index, row in enumerate(rows) if index not in rejected_indexes]
    for row in sorted(active_rows, key=lambda x: (x["item"], x["period"], x["claim_id"])):
        key = (row["item"], row["period"])
        if key in seen:
            bad.append(reject(row, "DUPLICATE_PERIOD", "同清单同周期重复申报"))
            continue
        seen.add(key)
        prev = number(overrides.get(row["claim_id"], row["previous_qty"]))
        current = number(row["cumulative_qty"])
        if prev < 0:
            raise DomainError("BAD_PREVIOUS", "前审累计量不能为负")
        incremental = current - prev
        if incremental < 0 and row.get("reversal") != "approved":
            bad.append(reject(row, "REVERSAL_REQUIRED", "负进度缺少已批冲回凭证"))
            continue
        record = {**row, "approved_previous": str(prev),
                  "increment_qty": str(incremental),
                  "gross_amount": str(incremental * number(row["unit_price"]))}
        # 迟到承接量对承接期的量价影响单独留痕。
        if record.get("late_claim"):
            record["late_increment_qty"] = record["increment_qty"]
            record["late_gross_amount"] = record["gross_amount"]
        good.append(record)

    return {"rows": good, "quarantine": bad,
            "metrics": {"accepted": len(good),
                        "negative_claims": sum(number(r["increment_qty"]) < 0 for r in good),
                        "late_accepted": sum(1 for r in good if r.get("late_claim")),
                        "late_quarantine": late_quarantine}}
