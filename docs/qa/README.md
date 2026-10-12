# OpsDesk AI Quality Engineering：交付导航

更新：2026-10-13。仅对应独立新版OpsDesk；历史阶段结论保留当时状态。

## 给GPT阅读

- **[最新Phase2C完整报告](PHASE2C_QUALITY_GATE.md)**：[Raw纯文本](https://raw.githubusercontent.com/SHAWNCHEN014/opsdesk-agent-service/main/docs/qa/PHASE2C_QUALITY_GATE.md)。
- **[全部阶段全文合并](DELIVERY_BUNDLE.md)**：[Raw纯文本](https://raw.githubusercontent.com/SHAWNCHEN014/opsdesk-agent-service/main/docs/qa/DELIVERY_BUNDLE.md)。包含审计、路线图、Phase2A/2B/2C五份原文，适合希望一次了解完整背景的阅读工具。
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

## 最新可复核证据

- [JUnit XML](evidence/phase2c-2026-10-13/after-commit/junit.xml)
- [JSON运行摘要](evidence/phase2c-2026-10-13/after-commit/summary.json)与[自动质量报告](evidence/phase2c-2026-10-13/after-commit/quality-report.md)
- [覆盖率](evidence/phase2c-2026-10-13/after-commit/coverage.json)、[逐模块风险](evidence/phase2c-2026-10-13/coverage-risk.json)
- [故意失败的退出码证明](evidence/phase2c-2026-10-13/gate-proofs/proof-summary.json)
- [证据哈希清单](evidence/phase2c-2026-10-13/manifest.json)、[原测试与历史报告完整性](evidence/phase2c-2026-10-13/integrity-check.json)
- [CI配置](../../.github/workflows/qa.yml)与[GitHub Actions实际运行列表](https://github.com/SHAWNCHEN014/opsdesk-agent-service/actions/workflows/qa.yml)

Phase2C最终实测业务版本：`1e801a300a0e0e7205fe2a7999a36022dc1939a4`；历史证据文档提交：`a4208a811d82cd02ba34cd94bb55236227fbbf13`。导航和合并文件不改变已验证业务代码。

**真实性边界：** 138项是含参数化的离线执行用例，原109项保留且全部通过；覆盖包含Mock和临时SQLite。该版本未执行真实Ollama/Chroma、MySQL并发及Redis恢复验收。Phase2C交付时远程CI尚未运行；推送后的真实状态以Actions记录为准，历史报告不会追溯改写。没有银行生产上线、获奖或性能提升结论。

## 本地复跑

```sh
python -m pip install -r requirements-dev.txt
python scripts/qa/run_checks.py
```

默认使用临时数据与离线替身，输出到新的artifacts/qa目录。失败退出1、不完整退出2；未运行的真实场景不计入passed。
