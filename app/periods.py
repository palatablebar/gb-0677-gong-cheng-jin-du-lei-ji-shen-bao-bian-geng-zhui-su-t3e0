"""期间状态与迟到申报承接规则。

业务背景：原计量批次所在月份已闭口（closed）后才发现的补录施工日志，
不得重开原月覆盖原批；由当前开放期（open）作为承接期代收，量计入承接期
出账，责任仍按原始属期溯源。期间状态由参数 periods 显式给出：
{"2026-08": "closed", "2026-09": "open"}。
"""
from app.errors import DomainError

CLOSED = "closed"
OPEN = "open"
VALID_STATUS = {CLOSED, OPEN}


def normalize(period_status):
    """校验期间状态表取值，返回归一化后的字典。"""
    if not isinstance(period_status, dict):
        raise DomainError("BAD_PERIODS", "期间状态需要对象")
    for period, status in period_status.items():
        if not isinstance(period, str) or len(period) != 7 or status not in VALID_STATUS:
            raise DomainError("BAD_PERIODS", f"期间状态非法：{period}={status}")
    return dict(period_status)


def open_periods(period_status):
    return sorted(p for p, s in period_status.items() if s == OPEN)


def check_late(spec, row, period_status):
    """校验单条迟到申报能否被承接。

    返回 None 表示通过；否则返回 (reason_code, detail)，由调用方隔离原行。
    """
    origin = spec.get("period")
    target = spec.get("carry_to")
    if not origin or not target:
        return ("BAD_LATE_SPEC", "迟到申报缺少原属期或承接期")
    if row.get("period") != origin:
        return ("LATE_PERIOD_MISMATCH",
                f"申报周期{row.get('period')}与迟到登记原属期{origin}不一致")
    if period_status.get(origin) != CLOSED:
        return ("LATE_PERIOD_NOT_CLOSED",
                f"原属期{origin}未闭口，应走当期正常申报而非迟到承接")
    if period_status.get(target) != OPEN:
        return ("CARRY_PERIOD_NOT_OPEN", f"承接期{target}未开放，不能代收")
    if origin == target:
        return ("CARRY_PERIOD_SAME", "承接期不能与原属期相同")
    return None


def carry_basis(origin, target, claim_id):
    """每条迟到记录附带的承接依据，随批次封存用于责任追溯。"""
    return (f"迟到补录：原属期{origin}已闭口，原批不得重开覆盖；"
            f"依据期间状态表由开放承接期{target}代收申报{claim_id}，"
            f"工程量计入{target}本期出账，责任与原始记录仍溯源至{origin}。")
