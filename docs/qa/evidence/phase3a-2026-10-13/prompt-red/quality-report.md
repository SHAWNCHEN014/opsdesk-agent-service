# OpsDesk 离线质量报告

门禁：**failed**；退出码：1
Git：`c7383c2d6e2ac2aeddae4aa9589365188287e313`；源码修改：True。实际版本以source_sha256为准。
Python：3.12.14；profile：offline / temporary SQLite / model-vector stubs / network connections blocked。

Pytest：165 passed / 4 failed / 0 errors / 0 skipped；合计169。
原109项：109通过；缺失/重复名单见JSON。
规则/BM25评估：passed；退出码0。

行覆盖：1067/1303 = 81.89%；分支覆盖：222/318 = 69.81%。
覆盖率只测Pytest中的业务模块；包括Mock路径，不代表真实基础设施验收。当前没有百分比门槛。

## 门禁理由

- pytest_failed

## 未关闭缺陷与残余风险

- 原审计登记缺陷在声明的离线范围内已关闭；不代表没有其他缺陷。
- direct线程永久阻塞及硬关闭时限尚未解决
- SMTP发送后提交失败可能产生重复通知
- 单进程原型的恢复、索引版本及数据库竞态仍需真实验收
- 覆盖率包含Mock执行，不说明真实模型语义质量或基础设施正确性

## not_run / 真实环境受阻

- real_mysql_redis：not_run；本轮未提供/连接专用真实服务；SQLite不验证MySQL行锁和Redis恢复
- real_ollama_chroma：not_run；默认离线profile禁止网络；模型与向量使用替身
- mcp_subprocess_faults：not_run；本轮未做stdio子进程超时/崩溃恢复演练
- docker_deployment：not_run；未启动容器或操作数据卷
- load_soak：not_run；未建立负载与长稳基线
- remote_ci：not_run；只配置并本地验证工作流；没有push或远程运行

远程CI未由本地报告证明；不得将not_run计入passed。
报告：junit.xml、summary.json、coverage.json/xml/txt、evaluation.json、pytest-output.txt。
