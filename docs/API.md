# 接口

模块GET使用仓内样例，模块POST可传csv或rows与context，直接计算当前规则。/api/runs使用完整流水线并原子保存。每个阶段返回rows、quarantine、metrics；后续阶段还返回累计隔离。/api/upload接收multipart文件file。/api/runs/<id>/archive只导出一份带清单与证据的CSV。

## 迟到承接与发布批次

闭口期后补录的施工日志按迟到申报处理，不重开原月、不覆盖原批：参数 `periods` 声明各期间 `closed/open` 状态，`late_claims` 登记 `{claim_id, period（原属期）, carry_to（开放承接期）}`。m4 累计还原把通过校验的迟到行周期改写为承接期，保留 `origin_period` 与 `carry_basis`，量计入承接期出账、责任溯源原属期；校验失败行进隔离区并从处理流剔除，血缘仍对平。

- `POST /api/batches`：body 为 `{sample|csv, parameters}`，生成可发布的本期计量批次草稿。批次身份为 sha256(输入+参数+规则版本)，同一输入重跑返回同一批次，不新增。
- `GET /api/batches`：批次清单；`GET /api/batches/<id>`：批次详情含 payload 与版本快照。
- `POST /api/batches/<id>/publish`：body `{version, fail?}`，乐观锁发布不可变版本快照；`fail:true` 演练发布失败，事务整体回滚并返回500，上一版保留可恢复。
- `POST /api/batches/<id>/rollback`：body `{version}`，追回当前已发布版，快照留存不删除。
- `POST /api/batches/<id>/restore`：body `{version（当前）, target_version（历史）}`，以历史快照生成新当前版本，旧版不被覆盖。
- 页面入口 `/batches`。陈旧版本写操作返回409；草稿不可追回，缺历史版本返回404。

