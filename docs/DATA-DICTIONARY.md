# 计量定义

claim_id唯一；item为清单编码，支持钢筋与001等别名。period为YYYY-MM。累计数量按t或m³保存，当前周期工程量=本次累计-前期已审累计。previous_revisions参数可指定更正后的前审数量，重新计算形成不同批次，不覆盖旧证据。

C0原始价100元，C1自2026-11生效为120元，DRAFT未批准不可结算。负进度必须reversal=approved作为已批冲回标记。扣留质保金5%、预付款扣回10%分别按分量化，净额=本期总额-质保金-预付款扣回，负进度同步冲回扣留。reported为原申报净额，差异=复算净额-reported。

业务ID和超大整数按文本保形；Decimal参与数量金额计算，对外序列化为字符串。哨兵集合定义在app/values.py，缺失值不能当零。所有时间带UTC偏移，先转UTC比较，业务日按指定地区划分。区间统一[start,end)。重复业务键保留第一条、完全相同行计重复；值冲突行隔离且保留原值。空文件、全空白、仅表头分开拒绝。

运行清单包括输入sha256、规则版本、参数、生成时刻与耗时。源行编号以CSV解析器的物理结束行号表示，引号内换行不增加记录数。输入超过4MB返回413，非法表头和类型返回422，失效版本复核返回409。

## 迟到申报承接

闭口期后补录的施工日志走迟到承接，参数而非新增输入列：`periods` 为 `{"YYYY-MM":"closed|open"}`，`late_claims` 为 `[{"claim_id","period"（原属期）,"carry_to"（承接期）}]`。校验规则：原属期必须 closed（否则 LATE_PERIOD_NOT_CLOSED）、承接期必须 open（CARRY_PERIOD_NOT_OPEN）、登记原属期须与申报行一致（LATE_PERIOD_MISMATCH）、两者不能相同、登记须能匹配到申报行（LATE_CLAIM_NOT_FOUND）。

通过的迟到行在 m4 改写 `period=carry_to`，附加 `origin_period`、`late_claim=true`、`carry_to`、`carry_basis`（承接依据文本）、`late_increment_qty`、`late_gross_amount`；工程量与净额计入承接期本期，原始属期与依据随批次封存用于责任溯源。批次 `payload.late_claims` 逐条说明承接期、量/价影响、依据或隔离原因，`impact_totals` 汇总迟到并入承接期的金额合计。发布批次号 `PB-序号`，版本快照在 `batch_versions` 表不可变留存。