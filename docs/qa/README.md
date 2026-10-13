# OpsDesk AI Quality Engineering：交付导航

更新：2026-10-13，Phase3A。仅对应独立新版OpsDesk；历史阶段结论保留当时状态。Phase3A源码、报告及证据已按用户授权推送GitHub；下列Raw链接可读取最新交付。

## 给GPT阅读

- **[最新Phase3A完整报告](PHASE3A_REAL_AI_EVALUATION.md)**：[Raw纯文本](https://raw.githubusercontent.com/SHAWNCHEN014/opsdesk-agent-service/main/docs/qa/PHASE3A_REAL_AI_EVALUATION.md)。
- **[22条独立人工核验表](evidence/phase3a-2026-10-13/real-final/HUMAN_REVIEW.md)**：包含输入、预期、实际答案及检索片段，全部待人工评分。
- **[全部阶段全文合并](DELIVERY_BUNDLE.md)**：[Raw纯文本](https://raw.githubusercontent.com/SHAWNCHEN014/opsdesk-agent-service/main/docs/qa/DELIVERY_BUNDLE.md)。合并六份原文，已同步GitHub。
- [版本及文件哈希](delivery-manifest.json)。如需固定某次交付，请使用GitHub页面的永久链接（将main换成该次完整commit），避免未来更新影响引用。

可把Raw链接直接交给支持网页访问的GPT，并说明：“请读取全文，以实际报告和证据为准；区分历史阶段与最新结果。如果无法访问或全文未读取，请明确告知，不要推测。”链接本身不保证所有GPT都具有网页读取权限。

## 分阶段交付

| 阶段 | 文件 | 当时结果 |
| --- | --- | --- |
| Phase1 | [代码和测试审计](OPSDesk_QA_AUDIT.md) | 原20项离线测试；识别质量风险 |
| 规划 | [AI Evaluation路线图](AI_EVALUATION_ROADMAP.md) | P0/P1/P2建设方案 |
| Phase2A | [四项缺陷闭环](PHASE2A_DEFECT_CLOSURE.md) | 79项通过 |
| Phase2B | [后台可靠性闭环](PHASE2B_RELIABILITY_CLOSURE.md) | 109项通过 |
| Phase2C | [测试工程化与门禁](PHASE2C_QUALITY_GATE.md) | 138项通过；行81.69%、分支69.11% |
| Phase3A | [真实AI专项评测](PHASE3A_REAL_AI_EVALUATION.md) | 离线174通过；真实检索61通过/5失败/18不确定；22条真实答案待人审 |

## 最新Phase3A可复核证据

- [真实AI JSON](evidence/phase3a-2026-10-13/real-final/results.json)、[JUnit](evidence/phase3a-2026-10-13/real-final/junit.xml)、[逐例JSONL](evidence/phase3a-2026-10-13/real-final/samples.jsonl)
- [最终离线174项摘要](evidence/phase3a-2026-10-13/final-offline/summary.json)、[JUnit](evidence/phase3a-2026-10-13/final-offline/junit.xml)、[覆盖率](evidence/phase3a-2026-10-13/final-offline/coverage.json)
- [缺陷记录](evidence/phase3a-2026-10-13/defect-closure.json)、[真实副作用和重复观察](evidence/phase3a-2026-10-13/observations.json)
- [原138项完整性](evidence/phase3a-2026-10-13/suite-comparison.json)、[历史文件完整性](evidence/phase3a-2026-10-13/integrity-check.json)、[证据manifest](evidence/phase3a-2026-10-13/manifest.json)

真实最终代码版本：`d2916aedb9e16fd46243221abe746ebf22dcfcd6`。同一模型/数据/知识库运行前后固定；Ollama qwen3:8b + nomic embedding + Chroma均实际执行。21项工作流确定性通过、1项故障分支未执行而不确定；安全7项指定边界defended、1项不确定。废止文档首位导致真实门禁退出1。人工评审0/22完成，不能宣称答案准确率或真实AI全绿。命令型输入的意图/建单策略仍待核验。

## 历史Phase2C证据

- [JUnit XML](evidence/phase2c-2026-10-13/after-commit/junit.xml)
- [JSON运行摘要](evidence/phase2c-2026-10-13/after-commit/summary.json)与[自动质量报告](evidence/phase2c-2026-10-13/after-commit/quality-report.md)
- [覆盖率](evidence/phase2c-2026-10-13/after-commit/coverage.json)、[逐模块风险](evidence/phase2c-2026-10-13/coverage-risk.json)
- [故意失败的退出码证明](evidence/phase2c-2026-10-13/gate-proofs/proof-summary.json)
- [证据哈希清单](evidence/phase2c-2026-10-13/manifest.json)、[原测试与历史报告完整性](evidence/phase2c-2026-10-13/integrity-check.json)
- [CI配置](../../.github/workflows/qa.yml)与[GitHub Actions实际运行列表](https://github.com/SHAWNCHEN014/opsdesk-agent-service/actions/workflows/qa.yml)

Phase2C最终实测业务版本：`1e801a300a0e0e7205fe2a7999a36022dc1939a4`；历史证据文档提交：`a4208a811d82cd02ba34cd94bb55236227fbbf13`。导航和合并文件不改变已验证业务代码。

**真实性边界：** Phase2C的138项是离线执行用例；Phase3A的174项包含原138项和新增36项，覆盖率82.03%/70.19%仍包含Mock和临时SQLite。Phase3A真实模型评测单独保存，不代表MySQL并发/Redis恢复验收。Phase2C历史版本首次Linux远程138项通过见[独立记录](evidence/phase3a-2026-10-13/previous-ci-confirmation.json)；Phase3A交付版本7d3f3c已完成Linux远程174项离线回归，全部通过；见[同步与CI验证](GITHUB_SYNC.md)。历史报告不改写。没有银行生产上线、获奖、全面防注入或性能提升结论。

## 本地复跑

```sh
python -m pip install -r requirements-dev.txt
python scripts/qa/run_checks.py
```

默认使用临时数据与离线替身，输出到新的artifacts/qa目录。失败退出1、不完整退出2；未运行的真实场景不计入passed。

真实profile不进入默认CI，需已有本地模型/Chroma与运行中的Ollama：

```sh
python scripts/qa/real_ai.py --profile real_ai_full --output artifacts/real-ai/new-run
```

支持real_rag、real_llm、real_ai_full及offline。目录必须新建；不下载模型。环境缺失退出2、确定性缺陷退出1，语义评审待完成也不能返回完整验收通过。详细前置条件及独立命令见Phase3A报告。

## GitHub同步约定

根据用户2026-10-13授权，今后本项目完成并验证的工作默认提交并推送现有origin。发布记录如实区分离线通过、真实AI失败及待人审结果。最新同步与CI证据见[GITHUB_SYNC.md](GITHUB_SYNC.md)。
