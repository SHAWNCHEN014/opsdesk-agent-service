# OpsDesk 离线质量报告

门禁：**passed**；退出码：0
Git：`d2916aedb9e16fd46243221abe746ebf22dcfcd6`；源码修改：True。实际版本以source_sha256为准。
Python：3.12.14；profile：offline / temporary SQLite / model-vector stubs / network connections blocked。

Pytest：174 passed / 0 failed / 0 errors / 0 skipped；合计174。
原109项：109通过；缺失/重复名单见JSON。
规则/BM25评估：passed；退出码0。

行覆盖：1077/1313 = 82.03%；分支覆盖：226/322 = 70.19%。
覆盖率只测Pytest中的业务模块；包括Mock路径，不代表真实基础设施验收。当前没有百分比门槛。

## 门禁理由

- 全部离线必需检查完成并通过

## 未关闭缺陷与残余风险

- QA-AI-FRESHNESS-01：open；真实检索5次废止文档排第一；保持失败证据，需有效期/替代关系设计，不用关键词改金标强行通过
- direct线程永久阻塞及硬关闭时限尚未解决
- SMTP发送后提交失败可能产生重复通知
- 单进程原型的恢复、索引版本及数据库竞态仍需真实验收
- 覆盖率包含Mock执行，不说明真实模型语义质量或基础设施正确性
- 真实AI正例HitRate@4=1不代表语义正确或知识时效合格；真实门禁因5次废止来源首位失败
- 22条最终真实答案的独立人工Rubric尚未完成；单模型/小合成集不代表泛化或全面注入防护

## not_run / 真实环境受阻

- real_mysql_redis：not_run；本轮未提供/连接专用真实服务；SQLite不验证MySQL行锁和Redis恢复
- real_ollama_chroma：not_run；本次默认offline profile不运行真实模型；Phase3A另有真实结果，见PHASE3A_REAL_AI_EVALUATION.md
- mcp_subprocess_faults：not_run；本轮未做stdio子进程超时/崩溃恢复演练
- docker_deployment：not_run；未启动容器或操作数据卷
- load_soak：not_run；未建立负载与长稳基线
- remote_ci：not_run；Phase3A新版本按要求未push，远程CI未运行；历史2edce8e的138项Linux通过记录见Phase3A previous-ci-confirmation.json

远程CI未由本地报告证明；不得将not_run计入passed。
报告：junit.xml、summary.json、coverage.json/xml/txt、evaluation.json、pytest-output.txt。
