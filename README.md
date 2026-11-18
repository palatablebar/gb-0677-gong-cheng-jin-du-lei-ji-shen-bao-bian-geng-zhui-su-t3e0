# 工程进度累计申报与变更追溯

供总包项目计量审核员核对原始记录、处理差异并封存证据。

## 启动

```sh
docker compose up --build -d
docker compose exec -T app pytest -q
```

打开 http://localhost:18246 。首次进入自动运行仓内脏样例。工具条可重跑、切换样例或上传CSV。SQLite保存在命名卷records中，重建服务保留批次。

## 模块

- 1. 申报采信：`/claims`，`/api/claims`。
- 2. 清单映射：`/billitems`，`/api/billitems`。
- 3. 变更定版：`/changes`，`/api/changes`。
- 4. 累计还原：`/increment`，`/api/increment`。
- 5. 扣回核算：`/deductions`，`/api/deductions`。
- 6. 进度对账：`/valuation`，`/api/valuation`。
- 7. 签证归档：`/certificates`，`/api/certificates`。
- 8. 批次发布：`/batches`，`/api/batches`（迟到承接、版本发布、追回与恢复）。

## 迟到申报与发布批次

八月批次闭口后才发现的施工日志补录，不重开原月、不覆盖原批。`periods` 声明期间 `closed/open`，`late_claims` 登记原属期与开放承接期；开放期代收迟到量并按九月出账，同时保留 `origin_period` 与 `carry_basis` 把责任溯源到原属期。每条迟到申报在批次中说明承接期、量/价影响与依据，校验失败行进隔离。

发布批次身份为 sha256(输入+参数+规则版本)，同一输入重跑不新增批次；每次发布生成不可变版本快照，旧版可追回（rollback）并可恢复为新版本（restore，不覆盖旧版）。发布走单事务，`fail:true` 可演练故障：失败整体回滚、上一版保留可恢复，陈旧版本写操作返回409。

## 核心规则

累计申报必须减前期已审金额，变更按审批生效版本覆盖；负进度需关联冲回证据。

## 演示

1. 打开首页，核对当次计算、差异和隔离原因。
2. 切换模块查看源行及裁决依据。
3. 重跑相同样例，批次号与行数保持一致。
4. 复核后导出一份证据CSV。版本已变化的复核提交返回409。

## 输入与输出

输入列见 `docs/DATA-DICTIONARY.md`。项目包含dirty.csv、clean.csv、legacy.csv，统一走实际导入路径。上传限制4MB，拒绝不带时区的时间。业务键按字符串保留，Decimal参与计算，空值不会当零。

`POST /api/runs` 接收sample或csv；`GET /api/runs`返回历史批次；`POST /api/runs/<id>/review`需要version与decision；`GET /api/runs/<id>/archive`返回唯一证据导出。

## 范围

样例均为虚构。单机复核工具不连接生产系统；不提供登录、远端数据库或自动支付。内存计算按4MB输入上限控制，SQLite事务保证结果完整写入。

## 目录

app为服务与规则，sample_data为输入，tests为测试，docs为定义与深度登记。
