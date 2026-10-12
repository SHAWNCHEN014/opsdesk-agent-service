# OpsDesk Phase 2A：缺陷修复与自动化回归闭环

日期：2026-10-13（Australia/Melbourne）。项目：独立重写版 `/Users/shawn/Desktop/OpsDesk`。

## 1. 结论与范围

**QA-SEC-01、QA-SEC-02、QA-RAG-01、QA-GATE-01 均已完成正式复现、根因定位、局部修复及离线回归，在本报告声明的场景范围内关闭。** 最终完整 Pytest **79 通过、0 失败、0 错误、0 跳过**；包含未修改的原有 20 个执行用例和新增 59 个用例。针对性回归 59/59 通过。

未接入新框架或依赖；业务改动只有 `opsdesk/orchestration.py`、`opsdesk/actions.py`、`opsdesk/retrieval.py`、`scripts/evaluate.py`。没有重构 Agent、修改队列、部署 CI、运行真实模型/数据库集成、改动真实业务数据或原有数据库卷。原始审计与证据保持原样，缺陷的历史开放状态由本报告补充后续处理结果。

本轮结果证明的是**本地原型的确定性行为及质量门禁**，不是生产可靠性、全面安全认证或模型语义准确率。

### 版本与证据

- 基线 HEAD：`925185f7238595733b115b0239ede8d669b37bb4`。
- 修复是当前未提交的工作区变更；没有编造修复 commit。完整运行的 [source_sha256](evidence/phase2a-2026-10-13/after/run-summary.json)、[源码差异](evidence/phase2a-2026-10-13/changes.patch)、修复前后源码快照及 [文件校验清单](evidence/phase2a-2026-10-13/manifest.json) 标识实际执行版本。
- [完整性核对](evidence/phase2a-2026-10-13/integrity-check.json)：原始四个源码快照与 HEAD 一致；前后最终测试及金标哈希相同；两个历史审计文档、历史证据、原有测试与 fixture 均未改变；`git diff --check` 退出 0。
- 机器记录：[缺陷关闭记录](evidence/phase2a-2026-10-13/defect-closure.json)、[分 Suite 对比](evidence/phase2a-2026-10-13/suite-comparison.json)。

## 2. Test → Fix → Regression 执行记录

首先完整阅读 `OPSDesk_QA_AUDIT.md`、`AI_EVALUATION_ROADMAP.md` 及 2026-10-13 的审计探针、测试/评测结果与校验清单，随后检查四个源码路径及现有 fixture。先新增测试，再执行原始代码，最后实施修复。

| 运行 | 通过 / 失败 / 错误 / 跳过 | 退出码 | 证据与含义 |
| --- | --- | ---: | --- |
| 首批测试 + 未修改业务代码 | 42 / 33 / 0 / 0（75项） | 1 | [before](evidence/phase2a-2026-10-13/before/run-summary.json)：四项缺陷均有失败；原20项通过 |
| 第一轮局部修复 | 74 / 1 / 0 / 0（75项） | 1 | [after-first](evidence/phase2a-2026-10-13/after-first/pytest-output.txt)：CRLF保真断言失败，继续修复，未降低断言 |
| 冻结最终测试 + 原始源码副本 | 42 / 37 / 0 / 0（79项） | 1 | [before-verified XML](evidence/phase2a-2026-10-13/before-verified/pytest.xml)、[日志](evidence/phase2a-2026-10-13/before-verified/pytest-output.txt)：临时复制必要源码/知识/Skills/网页，将四个文件换为基线快照；原20项通过 |
| 冻结最终测试 + 修复源码，完整集 | **79 / 0 / 0 / 0** | **0** | [after XML](evidence/phase2a-2026-10-13/after/pytest.xml)、[日志](evidence/phase2a-2026-10-13/after/pytest-output.txt)、[JSON](evidence/phase2a-2026-10-13/after/run-summary.json)；Pytest 7.962秒 |
| 修复源码，四个新增测试文件 | **59 / 0 / 0 / 0** | **0** | [targeted-after](evidence/phase2a-2026-10-13/targeted-after/run-summary.json)、[XML](evidence/phase2a-2026-10-13/targeted-after/pytest.xml)；Pytest 6.075秒 |

37 个失败是同一份最终测试对旧实现的失败断言，**不是37个独立缺陷**。包含新增的安全/保真边界和报告契约；旧实现的正确正向行为也被保留。第一次75项与最终79项是测试开发中两个版本，正式前后对照以哈希相同的79项为准。

### 隔离、异常与记录约定

Python 3.12.14，使用原项目 `.venv`、Pytest、TestClient/httpx、openpyxl、SQLAlchemy和标准库。执行从新临时工作目录启动，移除继承的 `OPSDESK_*`，不读取实际 `.env`，禁用第三方 Pytest 插件自动加载与 cacheprovider。所有 SQL、台账和评测数据均隔离；模型、embedding和向量结果使用受控替身；接口用例为 ASGI 测试，不能宣称真实服务验收。

保留一次中间的 `before-final/` 记录：新增混合降级场景的首次替身未覆盖 `embedding_identity`，触发了本机 Ollama `/api/tags` 连接尝试。因此该次记录**不作为无网络验证证据**。随后显式替换身份与 embedding，使用合成超时重新运行；正式 `before-verified/`、`after/`、`targeted-after/` 使用相同冻结测试与完整替身。该中间尝试没有执行模型生成、embedding或上传私有数据，未作为真实 Ollama 验收。

所有运行有一个既有 Starlette/httpx 弃用警告，未通过升级依赖掩盖。耗时是测试执行时间，不是用户响应延迟或性能提升。覆盖率仍未知；本轮未安装 coverage。真实 Ollama/Chroma/MySQL/Redis、Docker、负载/长稳、CI部署均未执行。

## 3. 四项缺陷闭环

### QA-SEC-01：危险建议与审查失败回退

**原始表现与根因**

`final_text_check` 原先从“不要 / Never / Do not”等词开始删除整段至句号。`不要担心，现在关闭公司的防火墙。` 中后半段的危险指令随之被删，检查返回 True。`ServiceTeam.solve` 的 review 节点捕获模型超时后，只记录 `review_model_unavailable`，继续保留先前的批准结果及草稿。这是“否定作用域错误 + 审查异常仍允许发布”两个连续问题。

**修复**

- [final_text_check](../../opsdesk/orchestration.py#L84) 逐个匹配危险动作和对象，只有紧接动作的否定表达可以排除该动作；不删除整个句子，不因单独出现“防火墙”“密码”等主题词而拒绝。
- 动作到对象使用非贪婪匹配，以便检查连续的第二个危险动作；`不要关闭防火墙但请关闭杀毒软件。` 不会共享第一个动作的否定作用域。
- review 节点在超时、异常或无法得到有效审查结果时，将草稿标记未批准，采用既有双语安全通用答复；保留 `approved=False`、`replacement_used=True`、降级标记及“review unavailable”理由。`approved` 表示原草稿批准与否，并非说替代答复还要被视为危险。
- 即使字符串检查没有覆盖某种语义表达，模型审查不可用时也不会发布原草稿。正常建议在审查成功时原样保留；审查故障时，正常建议同样降级，这是明确的可用性取舍。

**正式测试与证据**

[test_final_review.py](../../tests/qa/test_final_review.py)：23项，旧实现12通过/11失败，修复后23通过。覆盖正常中英文建议、直接否定、密码提醒、禁止 shell/删除命令、安抚语后的危险操作、中英混合正反指令、不要忘记、无标点连续动作、批准/拒绝、超时、坏审查响应，以及 regex 词表之外的可疑建议。团队测试断言实际发布文本、批准/替代/降级字段和审查调用次数，不只检查一个布尔值。复现用 `original-bypass` 与 `reassurance-zh`，详见修复前 JUnit。

**残余风险**：正则不是完整语言理解或全场景注入防御；正常表达覆盖是有限固定集合，未测全量误报率。正常运行依然依赖模型审查的语义判断；不能保证“危险内容绝不会输出”。本轮没有改变 demo 模式不调用模型审查的既有策略。

### QA-SEC-02：Excel 公式注入与文本保真

**原始表现与根因**

`ActionHandlers.export_ledger` 把用户摘要直接 `sheet.append`；openpyxl 将以 `=` 开头的字符串标为公式（`data_type='f'`），也会将 `#DIV/0!` 等标为 Excel error（`e`）。公式输入来自持久化工单摘要，即使模型输出已经审查，台账仍有独立的不可信输入路径。

**修复**

- [export_ledger](../../opsdesk/actions.py#L50) 对新增行的所有字符串显式设为文本单元格（`s`）。不添加会改变读回内容的单引号，不执行公式，不访问公式里的链接。
- 保留原有行去重、文件锁、同目录临时文件、原子替换和回执逻辑；原有列与导出时工单状态快照不变。
- 回归发现当前 XML 写入路径会输出原始 CR 字节，XML 读回时将 CRLF 规范化为 LF。[_save_literal_workbook](../../opsdesk/actions.py#L18) 在临时 XLSX 的 worksheet XML 中把 CR 写为合法 `&#13;` 字符引用，保持字符串精确读回；保留 ZIP 成员与压缩信息后再进行原子替换。

**正式测试与证据**

[test_ledger_text.py](../../tests/qa/test_ledger_text.py)：12项，旧实现7通过/5失败，修复后12通过。覆盖 `= + - @`、TAB/CRLF/空格前缀、Excel错误标记、中文/引号/`&<>`/emoji、多行文本、重复导出、追加工单、处理中状态及后续追加时旧行 CRLF 的保真。验证单元格类型及精确值、六列台账、工单/回执数量、ZIP校验、合法 worksheet XML、无公式元素及外部链接部件。原审计示例用 `equals` 复现。

**残余风险**：修复适用于之后新增导出行；没有批量转换既有工作簿的历史公式，也没有删除原有数据。未做真实 Excel 客户端或超大台账压力验收；ZIP重写有额外内存/文件写入成本。Excel单元格长度限制及非法 XML 控制字符仍受 openpyxl 约束，不宣称任意字节输入都能保真。

### QA-RAG-01：陈旧向量片段的安全降级

**原始表现与根因**

Chroma query 返回的片段 ID 未在当前 SQL `rows()` 中出现时，RRF先收录该 ID，随后标题重排/证据构造访问 `lookup[key]`。这一步在向量查询 try/except 之外，抛出未捕获的 KeyError。启动时校验索引并不能保证每次查询与 SQL 快照一致。

**修复**

- [KnowledgeIndex.search](../../opsdesk/retrieval.py#L139) 先建立 SQL 片段 lookup，再检查向量排名中的 ID。
- 任意未知/已删除 ID 导致当前向量通道整体舍弃，使用本次 SQL 数据的原 BM25 结果；不把部分陈旧向量结果继续混入证据。
- 将向量 `ready` 置 False，记录 `error='...rebuild required'` 及 `last_query_error='StaleVectorIndexError'`。本实例后续查询直接使用 BM25，避免重复查坏索引；恢复需要既有重建/有效恢复流程。
- RRF常数、标题加权、正常排名和 Evidence 字段保持不变。

**正式测试与证据**

[test_stale_vectors.py](../../tests/qa/test_stale_vectors.py)：6项，旧实现3通过/3失败，修复后6通过。使用真实 SQL/BM25/融合代码和受控身份、embedding及 collection。未知、混合有效/未知、已删除三种场景断言结果与纯 BM25 的完整 Evidence 严格相同、索引失效标志及下一次不再查询坏索引；另覆盖正常 RRF/标题重排的排名、分数和通道，向量超时记录，以及空库不查询向量。

**残余风险**：诊断状态仍为进程内状态，不是新的持久化日志/监控平台。没有真实 Chroma/Ollama 或多进程并发更新验收；SQL/索引的完整原子版本协调、索引重建中断恢复不在本轮范围。

### QA-GATE-01：规则与检索质量门禁

**原始表现与根因**

`scripts/evaluate.py` 原先只计算、保存及打印指标；入口运行 `asyncio.run(main())`，没有失败判定与退出状态。临时副本中优先级仅23/24正确，进程仍退出0；检索未命中同样如此。数据异常则可能产生 traceback，而无结构化“不完整”结果。

**本轮明确的通过标准**

| 项目 | 默认门禁 | 口径 |
| --- | --- | --- |
| 意图 / 优先级 | 两者均全部匹配（100%） | 现有24条确定性规则回归，不是LLM准确率 |
| Hit@4 | ≥1.0 | 现有12查询；返回前4片段中首次匹配预期 source 即命中 |
| MRR@4 | ≥0.90 | 首次匹配预期 source 的片段排名倒数均值；未命中记0 |
| 数据 | 分类与检索两组非空、格式/标签合法、参考文档存在 | 缺数据不能缩减分母后通过 |
| 检索模式 | vector关闭为BM25；vector开启必须可用且每条查询实际使用vector | 要求混合检索时不能把BM25降级报告为混合通过 |

之前没有阈值。本轮首次设置 MRR 0.90 为这一小型固定集的排序回归下限；原有一条参考 source 排名第3，基线 MRR=0.944444，因此没有规定所有查询必须rank1，也没有改金标迎合实现。它不是泛化质量指标或性能SLA。`--min-hit-at-4`、`--min-mrr` 可显式设置，报告记录实际标准；意图/优先级全匹配标准不可通过参数降低。测试明确将 `--min-mrr 1` 设为不达标场景，验证门禁不会擅自下调要求。

**修复与退出契约**

[evaluate.py](../../scripts/evaluate.py)：增加 CLI 输入/输出路径与有限范围阈值检查、数据契约验证、数据/知识哈希、运行profile、`status`及`gate`。保留原有分类/检索样例与算法和逐条指标。用临时 JSON 文件原子写入；数据库在 finally 中释放；错误记录阶段和异常类型，不打印敏感配置值。

- **0**：计算完整且标准全部满足，`status=passed`、`gate.passed=true`。
- **1**：计算完整，但指标不满足，`status=failed`、`gate.passed=false`，列出失败指标。
- **2**：输入/配置/语料/必需向量/查询/写报告异常或评估不完整，`status=error`、`gate.passed=false`。参数解析错误退出2并写 stderr，不产生假通过 JSON；输出不可写时 stdout 仍包含失败摘要。自动化必须检查退出码，不仅检查文件是否存在。

**正式测试与实际进程证据**

[test_evaluation_gate.py](../../tests/qa/test_evaluation_gate.py)：18项，旧实现18失败，修复后18通过。涵盖完整正向报告、意图/优先级不匹配、检索未命中、MRR阈值、缺文件/坏JSON/空集/无效标签/行格式、NaN/越界阈值、异常配置、缺语料、必需向量不可用、查询时混合降级、检索异常、报告写入失败。负例只操作临时副本，仓库 `evaluation/cases.json` 原样保留。

另外运行真实脚本 `__main__` CLI（仍为临时 SQLite/BM25）保存机器报告：[gate-after/summary.json](evidence/phase2a-2026-10-13/gate-after/summary.json)。

| 输入 | 旧脚本退出 | 修复脚本退出 / status |
| --- | ---: | --- |
| 原始24分类+12检索 | 0 | 0 / passed |
| 临时副本中一条priority预期不匹配 | **0** | **1 / failed** |
| 临时副本一条查询不匹配任何词 | **0** | **1 / failed** |
| 显式要求MRR≥1 | 0（参数原先未处理） | 1 / failed |
| 缺失输入文件 | 1（异常） | 2 / error |
| 空样例集 | 1（异常） | 2 / error |

原有数据的本轮 CLI 指标：意图24/24、优先级24/24、检索12条、Hit@4=1.0、MRR=0.9444444444444445、vector_queries=0，见[完整评测JSON](evidence/phase2a-2026-10-13/gate-after/baseline.json)。`run_gate_examples.py` 自身退出0表示这六种**预期退出状态**均正确；不是把故意失败的候选评估改记通过。

**残余风险**：评测仍是小型自写合成回归集；不评估真实模型生成、答案事实支持或泛化。沿用脚本默认配置读取方式及固定默认输出路径；直接在有业务数据的目录运行仍可能建表/seed或覆盖默认报告，所以使用以下隔离入口与独立输出。

## 4. 修改文件与新增资产

| 文件 | 变化 |
| --- | --- |
| `opsdesk/orchestration.py` | 否定作用域、逐动作检查、review异常安全替代 |
| `opsdesk/actions.py` | 新行显式文本类型、CR/CRLF的XML保真；保持锁/原子写/幂等 |
| `opsdesk/retrieval.py` | 陈旧ID校验、BM25整体降级及诊断 |
| `scripts/evaluate.py` | 输入/阈值/profile契约、哈希、门禁、原子报告、真实退出码 |
| `tests/qa/test_final_review.py` | 23个展开执行用例 |
| `tests/qa/test_ledger_text.py` | 12个展开执行用例 |
| `tests/qa/test_stale_vectors.py` | 6个展开执行用例 |
| `tests/qa/test_evaluation_gate.py` | 18个展开执行用例 |
| `docs/qa/evidence/phase2a-2026-10-13/` | 隔离重跑脚本、前后JUnit/日志/JSON、真实CLI报告、源码快照/patch、完整性及哈希清单 |
| 本报告 | 缺陷闭环、测试边界、风险、P0映射及可使用的成果口径 |

原 `tests/test_service.py`、`tests/conftest.py`、`evaluation/cases.json`、历史文档与审计证据没有修改。没有将新增参数化执行用例另外按函数数重复统计。

## 5. 可用于后续CI的本地命令

从任意目录执行，输出目录选择一个尚未保存测试结果的新目录：

```bash
/Users/shawn/Desktop/OpsDesk/.venv/bin/python /Users/shawn/Desktop/OpsDesk/docs/qa/evidence/phase2a-2026-10-13/run_pytest.py --output /tmp/opsdesk-phase2a-review-001
```

该入口使用临时工作目录及数据库，JUnit为 `pytest.xml`，机器摘要为 `run-summary.json`，原始断言输出为 `pytest-output.txt`，返回实际 Pytest 退出码。它可被后续CI调用，但本轮没有创建或远程部署CI。只运行新增回归可加 `--suite qa`；运行冻结测试对原始四文件快照可加 `--baseline`，预期退出1，并保留失败证据。

评测 CLI 的隔离成功/失败/错误示例可用：

```bash
/Users/shawn/Desktop/OpsDesk/.venv/bin/python /Users/shawn/Desktop/OpsDesk/docs/qa/evidence/phase2a-2026-10-13/run_gate_examples.py --output /tmp/opsdesk-phase2a-gate-review-001
```

实际命令会跑真实 CLI、隔离SQLite，并保留六类JSON/输出及每个子进程退出码。工具运行基线时才使用 `runpy` 重定向旧脚本固定 `PROJECT`，避免污染历史报告。解释器版本与依赖应以项目环境为准，后续执行不能直接沿用本次通过结果。

## 6. 与 Roadmap P0 的对应及未完成事项

| Roadmap项目 | 本轮完成 | 仍未完成 |
| --- | --- | --- |
| P0-1 缺陷复现/修复/回归 | SEC-01/02、RAG-01正式闭环 | **QA-REL-01/02仍开放**，未修改队列/Worker |
| P0-2 RAG与固定样例门禁 | 原24+12样例复用、坏ID/融合/空库/超时回归、QA-GATE-01 | 系统化分词/无答案集、人工金标扩充、真实混合评测 |
| P0-3 API/权限/模型矩阵 | 最终审查批准/拒绝/异常分支 | 大规模API/多员工矩阵与四角色全面故障测试 |
| P0-4 隔离与报告 | 本地隔离命令、JUnit/JSON/版本/hash/失败证据 | 行/分支coverage、统一全部任务的QA报告器 |
| P0-5 CI | 提供可调用入口与可失败退出状态 | CI尚未部署 |

QA-OBS-01人工重试审计仍开放。没有把这一轮四项关闭写成“全部P0已完成”。

下一轮 Phase 2B 优先处理 **Worker数据库异常后退出（QA-REL-01）与被依赖阻塞任务占满候选窗口（QA-REL-02）**：先正式故障注入/积压复现，再修复持续执行与可运行候选选择，验证恢复后状态、副作用和审计一致。人工重试操作者/原因记录可随后按授权补齐。

## 7. 能力与简历使用边界

本轮具备可追问的证据：参数化回归与风险用例设计、模型/向量替身和故障注入、临时数据库/文件隔离、真实脚本退出码测试、根因定位、最小修复、完整回归、JUnit/JSON及版本哈希保留。发现 CRLF 不保真后维持精确断言继续修复，未改金标或靠skip/xfail变绿。

可据实使用的中文简历表述：

> 围绕企业 IT Agent 开展测试开发与质量保障，基于 Pytest、临时 SQLite 及模型/向量替身构建安全输出、Excel导出、RAG检索与评测门禁回归；复现并修复4项缺陷，保留修复前失败证据和源码版本，完整回归79项通过，形成JUnit/JSON缺陷闭环记录。
>
> 为24条规则及12条检索合成样例实现质量门禁，区分通过、指标失败与评测异常，验证故意失败触发非零退出，提供隔离执行与机器报告入口。

不可据此宣称：银行生产测试/投产经历、生产可用性或性能改善、全场景prompt注入防御、真实模型准确率100%、真实MySQL/Redis故障恢复已验收、完整安全审计、coverage百分比或CI已上线。59项新增用例和79项通过是展开后的实际执行数量，不是新增59个测试函数。
