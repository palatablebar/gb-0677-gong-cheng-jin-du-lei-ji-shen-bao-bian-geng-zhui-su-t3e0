# 深度登记 工程进度累计申报与变更追溯

规模：中型。使用者：总包项目计量审核员。核心规则：累计申报必须减前期已审金额，变更按审批生效版本覆盖；负进度需关联冲回证据。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 申报采信 | 查看并运行申报采信 | `/api/claims` | `app/modules/m1_claims/rules.py` | `tests/test_m1.py` |
| M2 清单映射 | 查看并运行清单映射 | `/api/billitems` | `app/modules/m2_billitems/rules.py` | `tests/test_m2.py` |
| M3 变更定版 | 查看并运行变更定版 | `/api/changes` | `app/modules/m3_changes/rules.py` | `tests/test_m3.py` |
| M4 累计还原 | 查看并运行累计还原 | `/api/increment` | `app/modules/m4_increment/rules.py` | `tests/test_m4.py` |
| M5 扣回核算 | 查看并运行扣回核算 | `/api/deductions` | `app/modules/m5_deductions/rules.py` | `tests/test_m5.py` |
| M6 进度对账 | 查看并运行进度对账 | `/api/valuation` | `app/modules/m6_valuation/rules.py` | `tests/test_m6.py` |
| M7 签证归档 | 查看并运行签证归档 | `/api/certificates` | `app/modules/m7_certificates/rules.py` | `tests/test_m7.py` |
| 批次发布 | 迟到承接、发布、追回、恢复 | `/api/batches`、`/batches` | `app/batches/rules.py`、`app/batches/store.py` | `tests/test_batches.py` |

## 陷阱登记

| TRAP | 现象 | 朴素实现 | 本项目处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-01 | 旧编码 | 默认解码失败 | 回退GB18030 | `app/modules/m1_claims/rules.py` | `tests/test_m1.py::test_legacy_encoding_real_sample` |
| TRAP-02 | BOM | 首列名多字符 | utf-8-sig | `app/modules/m1_claims/rules.py` | `tests/test_m1.py::test_bom_real_sample` |
| TRAP-03 | 带引号换行 | 拆成两条 | csv逻辑行 | `app/modules/m1_claims/rules.py` | `tests/test_m1.py::test_quoted_newline_is_one_record` |
| TRAP-05 | 列数不匹配 | 静默错列 | 隔离原行 | `app/modules/m1_claims/rules.py` | `tests/test_m1.py::test_bad_columns_real_sample` |
| TRAP-08 | 前导零ID | 编码变形 | 全程字符串 | `app/modules/m1_claims/rules.py` | `tests/test_m1.py::test_identifier_preserved_real_sample` |
| TRAP-14 | 重复键冲突 | 后写覆盖 | 保留首条并隔离冲突行 | `app/modules/m1_claims/rules.py` | `tests/test_m1.py::test_duplicate_conflict_real_sample` |
| TRAP-18 | 空态三态 | 一律成功 | 分别错误码 | `app/modules/m1_claims/rules.py` | `tests/test_m1.py::test_three_empty_states` |
| TRAP-26 | 旧版本提交 | 覆盖新结果 | 版本条件更新 | `app/store.py` | `tests/test_e2e.py::test_stale_review_409` |
| TRAP-06 | 全角累计量 | 转换失败 | Decimal归一 | `app/values.py` | `tests/test_m2.py::test_fullwidth_quantity` |
| TRAP-07 | 累计量空值 | 按零冲回 | 隔离缺失 | `app/values.py` | `tests/test_m2.py::test_real_null_not_zero` |
| TRAP-10 | 分币舍入 | 浮点误差 | 分项量化后净额守恒 | `app/modules/m5_deductions/rules.py` | `tests/test_m5.py::test_fraction_rounds_to_cent` |
| TRAP-23 | 变更生效边界 | 旧价覆盖 | 按周期选择已批版本 | `app/modules/m3_changes/rules.py` | `tests/test_m3.py::test_effective_boundary` |
| TRAP-30 | 闭口期补录 | 重开原月覆盖原批 | 开放承接期代收，留原属期与依据 | `app/modules/m4_increment/rules.py`、`app/periods.py` | `tests/test_batches.py::test_late_claim_carried_to_open_period` |
| TRAP-31 | 迟到行被隔离后仍下游处理 | 同一来源行重复裁决 | 隔离即从处理流剔除，血缘对平 | `app/modules/m4_increment/rules.py` | `tests/test_batches.py::test_carry_quarantine_keeps_lineage_balanced` |
| TRAP-32 | 批次身份含时间戳 | 同输入重跑新增批次 | 摘要仅取输入+参数+规则版本 | `app/batches/rules.py`、`app/manifest.py` | `tests/test_batches.py::test_prepare_idempotent_same_input` |
| TRAP-33 | 发布故障半写 | 旧版被破坏无法恢复 | 事务提交/回滚，失败保留上一版 | `app/batches/store.py` | `tests/test_batches.py::test_failed_publish_rolls_back_and_keeps_previous` |
| TRAP-34 | 恢复覆盖历史 | 旧版丢失 | 恢复生成新版本，快照不可变 | `app/batches/store.py` | `tests/test_batches.py::test_rollback_then_restore_creates_new_version` |

## 对账规则

输入原始逻辑行=最终采纳来源行+隔离来源行+重复行+空白行+分段表头。派生记录用_sources保存完整来源，因此分组不丢行。业务预期合计与上游申报合计之差等于逐行差异之和。结果按输入摘要、规则版本及参数产生唯一批次，事务写入；同源重跑只复用已有批次。

迟到承接在 m4 处理：通过校验的迟到行原地把周期改写为开放承接期并封存原属期与依据；拒收行进隔离区即从处理流剔除，避免下游 m6 血缘重叠，来源行依旧对平。发布批次（app/batches）与计量 runs 表分离，原月已发布批次不被重开或覆盖；批次身份复用稳定摘要 digest(raw, params)，不含 generated_at 时间戳，保证同源重跑幂等。发布、追回、恢复均为单事务，连接显式 commit/rollback/close；恢复以历史快照另出新版本，batch_versions 中旧快照不可变。

## 已知不覆盖

4MB以上文件需预先按业务键分批；不模拟生产支付与外部回调。人工复核只变更批次状态，不改写原始记录。
