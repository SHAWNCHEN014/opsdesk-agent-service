# OpsDesk Phase 2C：测试工程化与质量门禁

日期：2026-10-13（Australia/Melbourne；机器日志使用 UTC）。范围仅为独立重写版 `/Users/shawn/Desktop/OpsDesk`。这是本地原型的离线质量工程记录，不是银行生产系统验收或投产批准。

## 1. 结论与工程基线

- 开始时工作区干净，HEAD 为 `97f30fb33c56fbf00f04061a6a30b4d071e8a8a4`，业务源码与用户指定的 Phase 2B 基线 `6012e8898cc17eb20160bdb0321e12ad3206cbba` 一致；前者增加了 Phase 2B 证据文档。
- 完整阅读 Phase 1 审计、路线图及 Phase 2A/2B 闭环报告，重新运行原有 **109 项，全部通过**。原测试文件及原评测金标未修改；历史审计、证据文件未改写。
- 本轮新增 **29 个参数化执行用例**：人工重试审计 11、健康检查 3、门禁基础设施 15。最终 **138 passed / 0 failed / 0 errors / 0 skipped**；原 109 项逐个核对身份，全部保留并通过。
- QA-OBS-01 在声明的离线场景内闭环；额外确认并修复 QA-HEALTH-01（数据库异常使健康接口返回非结构化 500）。
- 首次测量原基线及修复后行、分支覆盖率。修复后 **行 1053/1289 = 81.69%，分支 217/314 = 69.11%**。没有设置任意百分比门槛。
- 统一命令生成 JUnit、JSON、Markdown 和覆盖率报告。临时副本中的故意失败确实返回退出码 1；缺失评测数据返回 2。
- 已编写 GitHub Actions 配置，使用新建的最小依赖环境完成本地验证。**没有 push、没有远程 CI 运行，没有设置远程分支保护，不能宣称 CI 已上线或 PR 合并已受保护。**

代码与测试提交：`1e801a300a0e0e7205fe2a7999a36022dc1939a4`（本地）。提交后复跑的源码 Git 状态干净。后续证据文档提交不会改变已测业务代码；该提交身份可从 `git log` 查到。[版本记录](evidence/phase2c-2026-10-13/versions.json)与[完整性检查](evidence/phase2c-2026-10-13/integrity-check.json)保留原测试、历史报告及金标 SHA-256 校验。

## 2. QA-OBS-01：人工恢复审计闭环

### 2.1 原始行为与根因

Phase 2B 的 `ActionWorker.retry()` 校验状态后直接将 DEAD 动作重置为 READY，未写入可归属操作者的 `ActionHistory`。FastAPI 接口没有恢复原因输入契约，普通员工在工程师依赖检查处被拒绝，未留下该次拒绝处置记录。旧的自动执行审计无法证明“谁在何时为什么重试了哪个动作”。

复现先于业务修复。初次增加 14 个业务回归执行用例后，旧业务实现执行 123 项：110 通过、13 失败。最后冻结全部 138 项测试，在临时 Git 副本中仅恢复三个 Phase 2B 业务文件，得到 **125 通过、13 失败**：人工审计 10 个失败、健康检查 3 个失败；匿名拒绝这一原有正确行为仍通过。13 个红断言不是 13 项缺陷。[最终修复前 JUnit](evidence/phase2c-2026-10-13/before-final/phase2b_business_baseline/junit.xml)与[对照摘要](evidence/phase2c-2026-10-13/suite-comparison.json)可复核。

### 2.2 最小修复

源码：[Worker.retry](../../opsdesk/queueing.py)、[FastAPI retry](../../opsdesk/main.py)、[ManualRetryInput](../../opsdesk/contracts.py)、[既有 ActionHistory](../../opsdesk/storage.py)。

1. HTTP 接口从认证身份取得操作者 ID，Worker 再核对数据库中角色必须为 `engineer`。普通员工返回 403 并记录拒绝；未登录返回 401。请求体不能指定或伪造操作者。
2. 恢复原因只接受 `issue_resolved`、`dependency_restored`、`operator_reviewed` 三种代码；禁用任意自由文本及多余字段，非法输入返回 422。旧页面不带请求体时使用 `operator_reviewed`，保持原调用兼容。
3. 同一 SQL 事务完成队列重置和审计写入；审计失败时两者均回滚，接口返回安全的 503，动作维持原 DEAD 状态和重试次数。
4. 合法恢复沿用原语义：仅 DEAD 可重试、依赖必须 DONE、重置本次重试预算、清理租约；旧 FAILED 历史保留。`attempt` 保存重置前次数，`before/after` 保存 phase/tries，不能通过删除历史掩盖恢复。
5. 状态冲突等拒绝先提交拒绝审计，再向接口抛出安全的业务错误；缺失动作、非 DEAD、重复请求及依赖未完成均返回 409，队列不变。

审计字段：`action_id`；既有 `created` UTC 时间；`MANUAL_RETRY_ACCEPTED/REJECTED`；`transport=manual`；`detail.actor={kind,id,role}`；原因代码、处置 outcome、前后状态。只保存身份 ID，不复制用户名、密码、Cookie、Token、原异常详情或租约值。原先失败异常中的合成凭证没有复制到新人工审计。

恢复路径继续支持可信内部 Python 调用 `retry(action_id)`，但明确标记为 `kind=system`，不冒充工程师；HTTP 路径始终传入认证身份。它是进程内部兼容接口，不能称为完整 RBAC。

### 2.3 测试与边界

[test_retry_audit.py](../../tests/quality/test_retry_audit.py)的 11 项验证：

| 场景 | 断言及实际结果 |
| --- | --- |
| 工程师合法恢复 | 身份、时间范围、原因、旧历史、重置前次数和状态正确；继续执行后恰好 1 工单、1 台账回执 |
| 普通员工/匿名 | 分别 403/401；员工拒绝被归属记录，动作不变；匿名在认证阶段拒绝 |
| 动作不存在/非 DEAD/依赖未完成/串行重复 | 409，拒绝 outcome 正确、前后状态相同，无第二次预算重置 |
| 任意秘密样式原因/伪造 actor_id | 422，任务不变，不持久化这些请求体字段 |
| 审计写入 SQL 故障注入 | 503，无部分提交，DEAD/tries=3 保留；响应不含合成秘密 |
| 可信内部调用 | 明确记录 system 身份，不伪造工程师 |

**数据兼容性：** 本轮没有改表、DDL、数据库卷或真实数据；复用 `ActionHistory` 的字符串和 JSON 字段，新增结果代码适配现有字段长度。无需迁移。回滚业务代码不需要删除新增审计行；旧诊断接口能读取它们。回滚到旧代码会失去新的审计写入保障，不应将这种回滚视作等价的质量版本。

**审计边界：** 匿名 401、请求体 422 在进入可归属恢复逻辑前拒绝，不伪造操作者审计；SQL 本身不可用时无法在同一 SQL 库持久记录该失败，只能返回 503并记录异常类型，保证动作未改变。当前诊断接口展示结果/detail，时间保存在 SQL 的 `created`，没有新增完整审计查询产品。真实 MySQL 行锁、并发人工重试、身份删除与恢复的竞态未验证；串行重复请求验证不等于并发事务验证。自动执行 `finish()` 仍可能保留原异常文本，未在本轮全局重做日志脱敏。

## 3. 健康检查异常路径

原 `/api/health` 在 session 获取或 `SELECT 1` 抛出 SQLAlchemy 异常时，异常直接逃逸，TestClient（关闭异常重抛）实际收到 HTTP 500。本轮在上述隔离边界注入 `OperationalError`，修复后得到结构化 503：

```json
{
  "status": "degraded",
  "database": {"status": "unavailable", "error": "OperationalError"}
}
```

实际完整响应同时保留 project、model_mode 和既有 worker 状态。只返回异常类型，日志也只记录类型，不返回 SQL、DSN 或异常消息。移除故障注入后恢复 200，database=ok；禁用 Worker 是有效配置，不被误判为 Worker 故障。[3 项正式测试](../../tests/quality/test_health_database.py)全部通过。

边界：该修复验证的是运行中 SQL 查询/连接异常；启动阶段 `Database.ensure()` 失败、Redis/模型/向量的健康探测未扩展，本轮没有建立完整监控平台。

## 4. 首次覆盖率基线与缺口

开发依赖新增 `coverage==7.16.2`，分支测量配置在 [pyproject.toml](../../pyproject.toml)。没有修改运行依赖锁定文件。使用 pip 的 `-c requirements.txt` 复用已有版本约束，新增 [requirements-dev.txt](../../requirements-dev.txt) 仅安装离线 QA 需要的包，不要求安装 Chroma/ONNX。新建的独立 Python 3.12.14 虚拟环境安装成功、`pip check` 成功、138 项通过。

| 测量版本 | 行覆盖 | 分支覆盖 | 未覆盖行 / 分支 |
| --- | --- | --- | --- |
| Phase 2B 业务 + 原109项 | 1017/1258 = 80.84% | 209/306 = 68.30% | 241 / 97 |
| Phase 2C 提交 + 138项 | 1053/1289 = 81.69% | 217/314 = 69.11% | 236 / 97 |

原基线证据：[coverage-baseline109](evidence/phase2c-2026-10-13/coverage-baseline109/summary.json)。最终：[coverage.json](evidence/phase2c-2026-10-13/after-commit/coverage.json)、[coverage.xml](evidence/phase2c-2026-10-13/after-commit/coverage.xml)、[coverage.txt](evidence/phase2c-2026-10-13/after-commit/coverage.txt)、[逐模块风险数据](evidence/phase2c-2026-10-13/coverage-risk.json)。新增审计和健康处理改变了分母；这两个版本的差异不能解释成线上缺陷率、性能或 AI 质量提升。

测量包括 Pytest 进程中的 `opsdesk` 业务包全部模块，**没有排除低覆盖模块来抬高数字**；`excluded_lines=0`。coverage 的汇总 `percent_covered=79.23%` 混合行与分支，不应当作行覆盖率。最终仍有 47 个 partial branches。QA 脚本和独立评测子进程不在这个业务包覆盖分母中，其行为由正式门禁测试及命令级失败证明检查。

| 模块 | 行覆盖 | 分支覆盖 | 下一阶段风险与证据边界 |
| --- | --- | --- | --- |
| inference.py | 9/43，20.93% | 0/10，0% | 真实 Ollama HTTP、生成、embedding、模型核验未默认执行 |
| action_server.py | 0/21，0% | 0/2，0% | Worker MCP stdio 服务进程未进入本次覆盖采集 |
| history.py | 25/43，58.14% | 3/10，30% | Redis 缓存与故障恢复路径缺少真实服务验证 |
| retrieval.py | 112/150，74.67% | 39/52，75% | 真实向量召回、重建/恢复及知识导入异常需要专项验证 |
| main.py | 210/260，80.77% | 29/48，60.42% | 部分 HTTP MCP、知识导入、SSE/接口异常路径未覆盖 |
| queueing.py | 149/172，86.63% | 50/64，78.13% | MCP invoke、真实数据库竞态、永久阻塞等残余风险 |
| storage.py | 112/112，100% | 5/6，83.33% | SQLite 执行了源码不能证明 MySQL 行锁、迁移或生产持久性 |

模型和向量替身、临时 SQLite、真实临时 Excel 是离线证据。代码行执行不说明模型答案正确、提示注入被真实模型抵抗、所有输入边界通过，也不能把现有类定义被执行称为全部契约已验证。

## 5. 统一测试入口与门禁契约

入口：[scripts/qa/run_checks.py](../../scripts/qa/run_checks.py)。在项目目录使用现有 `.venv`：

```sh
cd /Users/shawn/Desktop/OpsDesk
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/qa/run_checks.py
```

最后一条命令自动创建 `artifacts/qa/<UTC时间>`；也可指定新的输出目录：

```sh
.venv/bin/python scripts/qa/run_checks.py --output artifacts/qa/manual-check-001
```

已存在的目录会被拒绝，不覆盖历史结果。使用独立最小虚拟环境时，将 `.venv/bin/python` 换成该环境的解释器即可。不要将遗留 Phase 2A/B 证据目录当作新的输出目录。

### 5.1 流程、产物与隔离

1. 记录 HEAD、源码 dirty 状态、Python/操作系统/依赖版本及源码/测试/知识/金标/config SHA-256，不打印环境变量全集。
2. 在临时目录中执行覆盖率 + 全量 Pytest，生成 JUnit。核对 [baseline_cases.json](../../scripts/qa/baseline_cases.json) 中原109项身份，防止删用例后总数仍相似的假通过。
3. 运行既有 `scripts/evaluate.py`，沿用原24条规则金标、12条检索金标及原门槛，不修改金标迎合实现。
4. 生成 `junit.xml`、`summary.json`、`quality-report.md`、`coverage.json/xml/txt`、`evaluation.json`、原始测试/评测输出。JSON逐例区分 passed/failed/errors/skipped，单列 not_run，包含未关闭登记缺陷与残余风险。

子进程不继承 HOME、密钥、代理及真实服务配置；工作目录是临时目录，不加载本机 `.env`。显式使用临时 SQLite、demo 模型、关闭向量与 Redis、direct 传输、record 通知和隔离输出。默认禁止自动发现第三方 Pytest 插件。[offline_guard.py](../../scripts/qa/offline_guard.py) 对 Pytest 和独立评测脚本禁用 Python socket connect/connect_ex/create_connection。该保护是 Python 层连接保护，**不是操作系统级沙箱**；不声称能约束任意恶意原生扩展或额外程序。

JUnit 去除 hostname、临时路径和可识别凭证样式；报告采用环境/文件白名单。此次没有读取或上传真实数据库、`.env`、用户档案、密钥或运行卷。报告只含隔离测试与合成案例。

### 5.2 通过标准

| 退出码 | 含义及典型情况 |
| --- | --- |
| 0 | 必需离线 Pytest、原109项身份、覆盖率测量和既有评估全部完成并通过，没有登记的开放阻断缺陷 |
| 1 | 测试失败/error/非预期skip、原用例缺失/重复、评估不达标或登记阻断缺陷开放 |
| 2 | 配置/依赖/数据问题、采集失败/中断、零测试、覆盖率无法生成、评估无法完成、运行中源码变化或 Git 元数据缺失 |

覆盖率门禁目前要求**测量成功且含分支**，不要求任意80%/90%。未来应依据关键风险路径及历史波动设计规则，而不是为了数字补无意义测试。`closed_offline` 表示登记缺陷在对应场景内闭环，不代表全系统无缺陷；not_run 永远不计入 passed。

本次既有规则/BM25评估：24条意图/优先级各24条正确；12条检索 Hit@4=1.0、MRR=0.944444；通过原门槛（两类准确率=1、Hit@4≥1、MRR≥0.9）。`profile=bm25`、`vector_queries=0`，不能将此结果写成真实 Chroma 或 LLM 准确率，也不是100条旧项目评测。[实际评测结果](evidence/phase2c-2026-10-13/after-commit/evaluation.json)。

## 6. 实际回归与可复现失败证明

| 运行 | passed / failed / errors / skipped | 实际退出状态 |
| --- | --- | --- |
| 初始 Phase2B 重验 | 109 / 0 / 0 / 0 | Pytest 0 |
| 最终冻结测试 + 旧业务三个文件（临时副本） | 125 / 13 / 0 / 0 | 门禁 1；原109项仍通过 |
| 新最小依赖环境 | 138 / 0 / 0 / 0 | 门禁 0；pip check 0 |
| 最终提交后全量 | 138 / 0 / 0 / 0 | 门禁 0；源码干净、原109项通过 |
| 临时副本增加故意失败测试 | 138 / 1 / 0 / 0 | 门禁 1，pytest_failed |
| 临时副本改变一条金标制造不达标 | 137 / 1 / 0 / 0 | 门禁 1，evaluation_failed；Pytest也发现该不匹配 |
| 临时副本移除评测数据 | 125 / 13 / 0 / 0 | 门禁 2，evaluation_incomplete；不记录为通过 |

最后三行执行的是 CI 配置中的**同一条 CLI**，候选的非零退出码保存在 [gate-proofs/proof-summary.json](evidence/phase2c-2026-10-13/gate-proofs/proof-summary.json)。其复现驱动脚本自身返回0表示“预期失败已被证明”，不表示失败候选通过。改金标与删文件仅发生在临时本地 Git 副本，原仓库金标和测试保持原样。

最终证据：[JUnit](evidence/phase2c-2026-10-13/after-commit/junit.xml)、[JSON](evidence/phase2c-2026-10-13/after-commit/summary.json)、[自动 Markdown](evidence/phase2c-2026-10-13/after-commit/quality-report.md)。复现脚本位于 `evidence/phase2c-2026-10-13/run_gate_proofs.py`，可用 `--mode failures` 或 `--mode baseline` 和全新 `--output` 重跑，默认不访问远程。

中间运行也保留：修复业务后初次123项中有2项失败来自新测试错误地假设退出TestClient上下文必定设置httpx的 `is_closed`，实际健康503断言已通过。修正测试生命周期处理后完成冻结红/绿对照，没有降低业务断言、修改原109项或更改金标。初次统一运行正确返回1。`precommit-check` 保留一次提交前运行（文件夹曾提前命名，后改名，内容未改写），Git信息正确显示提交前状态。详见 [intermediate-notes.json](evidence/phase2c-2026-10-13/intermediate-notes.json)。

## 7. 最小 CI 配置与验证边界

[.github/workflows/qa.yml](../../.github/workflows/qa.yml) 使用已有 GitHub 托管平台：push main、pull_request、手动触发；Ubuntu 24.04 / Python 3.12；安装最小 QA 依赖；运行上述统一命令，无 continue-on-error 或故障绕过。权限 contents:read，checkout 不持久保存凭证。

官方 action 的 v7 引用经公开标签核验后固定完整 SHA；checkout、setup-python、upload-artifact 的行为依据各自官方文档。[checkout](https://github.com/actions/checkout)、[setup-python](https://github.com/actions/setup-python)、[upload-artifact](https://github.com/actions/upload-artifact)。运行后 `always()` 仅保存八个白名单报告文件，保留14天，不上传仓库全集、本机环境或业务数据。必要失败详情在 JUnit 和脱敏测试输出中。

本地已验证 YAML、步骤契约、权限、SHA固定和制品名单；新建 **Darwin** 虚拟环境实际安装并跑通138项，不代表 Ubuntu runner 上安装已验证。故意失败通过工作流同款 CLI 本地确认非零。[ci-validation.json](evidence/phase2c-2026-10-13/ci-validation.json)。

**真实状态：远程 CI 尚未验证。** 未推送任何本轮提交，未改变仓库可见性或访问权限，未设置 required check/分支保护。配置中的 job 会传播失败退出状态；但没有远程 run、artifact 或真实 PR 合并阻断证据。后续用户授权 push 后，应观察首次真实绿色运行及一次安全失败候选，再单独决定是否设置分支保护。

## 8. 修改清单、证据与残余风险

| 文件 | 变化 |
| --- | --- |
| opsdesk/queueing.py | 事务内人工恢复审计、身份/状态/原因校验、拒绝审计与回滚 |
| opsdesk/main.py | 认证身份传递、安全503、结构化数据库健康失败 |
| opsdesk/contracts.py | 最小恢复原因契约及禁止额外字段 |
| tests/quality/test_retry_audit.py | 11个身份、失败、重复、依赖、成功及原子性场景 |
| tests/quality/test_health_database.py | 3个数据库连接/查询异常及恢复场景 |
| tests/quality/test_quality_gate.py | 15个门禁、JUnit、数据完整性、隔离与CI配置场景 |
| scripts/qa/run_checks.py、offline_guard.py、baseline_cases.json | 统一执行、连接隔离、原109项身份契约 |
| requirements-dev.txt、pyproject.toml、.gitignore | 最小离线依赖、覆盖率配置及生成物忽略 |
| .github/workflows/qa.yml | 最小原生CI配置，尚未远程执行 |
| docs/qa/quality-status.json | 当前登记缺陷/残余风险/not_run；不覆盖历史报告 |

源码变更14个路径（包含配置、测试及状态文件），快照在 `after-source/`，完整patch在 `changes.patch`。机器闭环见 [defect-closure.json](evidence/phase2c-2026-10-13/defect-closure.json)。证据 [manifest.json](evidence/phase2c-2026-10-13/manifest.json) 保存 SHA-256（不含自身），供后续核对。

本轮未启动真实 Ollama/MySQL/Redis/Chroma、未操作原数据卷，未进行Docker部署、压力/长稳或MCP stdio故障演练。2026-09-28 的历史真实验收不能替代 Phase2C 版本的验收。Phase2B遗留的direct线程永久阻塞/关闭时限、SMTP发送与SQL提交间重复通知窗口仍存在；此次没有扩大为监控或调度重构。模型安全的离线替身通过不等于真实模型对所有危险建议均安全。

原路线图的P0人工审计、可复现回归和基础门禁现已具备离线证据；真实数据库并发、AI质量及运行保障剩余验收继续单列。没有发现原109项回归，不能因此断言不存在未测试问题。

## 9. 下一阶段：真实 AI 专项评估

建议 Phase3 使用现有 Pytest、JSON 金标与统一报告，分开新增可选择的真实 profile，不让默认离线 CI 依赖本机模型：

1. **真实 Ollama 基线。** 记录模型/embedding名称与digest、提示词、代码/知识/数据集版本；使用专用合成IT场景，验证模型不可用、超时、畸形结构化输出及恢复。记录实际检索/生成/审查/工具及端到端耗时，真实测量后再确定性能标准。
2. **真实 RAG。** 单独评测BM25、Chroma向量和混合重排，记录召回片段及引用；明确断言真实向量被调用，避免静默BM25回退冒充向量通过。增加冻结保留集、双语、无答案、过期知识和注入文档；以Hit@k/MRR/引用支持度区分检索与生成问题。
3. **真实 Agent 和故障处置。** 固定FAQ/报修/多人中断/危险建议轨迹，检查角色节点、工具参数/次数/顺序、降级及最终引用。确定性状态、权限与副作用用断言；语义正确、引用支持度及可用性采用人工样本复核，不能让同一模型的自评充当唯一金标。
4. **专用基础设施验收。** 独立MySQL/Redis实例与测试卷验证并发重试、行锁/租约、恢复和幂等；MCP stdio真实调用及崩溃超时另成场景。分别展示passed/failed/not_run，保留失败案例和版本，不触碰原业务数据。

需要用户后续确认真实环境资源、模型版本和运行成本/时间预算；本轮没有启动这些工作。暂不引入Ragas/DeepEval/Locust，待现有指标与真实数据采集稳定后再评估收益。

## 10. 金融科技测试运营岗位可用表述

可描述为：**围绕企业IT服务台Agent构建Pytest离线自动化回归与质量门禁，138项执行用例全部通过；通过SQL故障注入验证人工恢复审计原子性、权限限制及健康降级，保存红/绿JUnit、JSON、源码版本和SHA-256证据；建立行81.69%、分支69.11%的首次覆盖率基线，并以故意失败验证门禁退出契约，完成最小GitHub Actions配置和本地验证。**

Phase2A/2B/2C累计8项登记质量缺陷在各自离线范围闭环（4+2+本轮人工审计及健康检查2）；不能称为8项安全漏洞。138=20+59+30+29，含参数化执行；覆盖率和固定规则/BM25结果不是LLM语义准确率。可证明测试开发、故障注入、权限/事务回归、证据追溯及门禁工程能力。不能宣称银行生产上线、远程CI上线、MySQL并发验收、可用率/SLA、真实AI安全保证或性能提升。
