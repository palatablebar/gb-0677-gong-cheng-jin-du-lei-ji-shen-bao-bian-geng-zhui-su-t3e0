REASONS={"BAD_COLUMNS":"列数不匹配","EMPTY_VALUE":"必填值为空","INVALID_NUMBER":"数字格式错误","INVALID_TIME":"时间缺少偏移或格式错误","DUPLICATE_CONFLICT":"同键取值冲突","UNKNOWN_REFERENCE":"引用不存在","STALE_VERSION":"版本已更新","EMPTY_FILE":"文件为空","HEADER_ONLY":"仅有表头","BLANK_ONLY":"全部为空行","LATE_PERIOD_MISMATCH":"迟到登记属期不一致","LATE_PERIOD_NOT_CLOSED":"原属期未闭口","CARRY_PERIOD_NOT_OPEN":"承接期未开放","CARRY_PERIOD_SAME":"承接期与原属期相同","BAD_LATE_SPEC":"迟到登记缺字段","LATE_CLAIM_NOT_FOUND":"迟到申报无对应行"}
def reject(row, code, detail):
    return {**row,"reason":code,"detail":detail}
def sources(row):
    return row.get("_sources", [row.get("_line",0)])
