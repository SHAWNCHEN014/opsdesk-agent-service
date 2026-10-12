# 真实AI评测运行摘要

Git：c7383c2d6e2ac2aeddae4aa9589365188287e313；profile：real_ai_full；门禁：{'exit_code': 1, 'status': 'failed', 'reason': 'recorded_deterministic_findings'}

固定正例检索指标（不等于答案质量）：
```json
{
  "bm25": {
    "queries": 28,
    "positive_queries": 22,
    "counts": {
      "passed": 20,
      "failed": 2,
      "inconclusive": 6
    },
    "hit_rate_at_4": 1.0,
    "mrr_at_4": 0.9318181818181818,
    "mean_source_recall_at_4": 1.0
  },
  "hybrid": {
    "queries": 28,
    "positive_queries": 22,
    "counts": {
      "passed": 21,
      "failed": 1,
      "inconclusive": 6
    },
    "hit_rate_at_4": 1.0,
    "mrr_at_4": 0.9545454545454546,
    "mean_source_recall_at_4": 1.0
  },
  "vector": {
    "queries": 28,
    "positive_queries": 22,
    "counts": {
      "passed": 20,
      "failed": 2,
      "inconclusive": 6
    },
    "hit_rate_at_4": 1.0,
    "mrr_at_4": 0.9545454545454546,
    "mean_source_recall_at_4": 1.0
  }
}
```

计数：
```json
{
  "retrieval": {
    "passed": 61,
    "failed": 5,
    "inconclusive": 18
  },
  "agent_deterministic": {
    "passed": 19,
    "failed": 2,
    "inconclusive": 1
  },
  "answer_quality": {
    "needs_human_review": 20,
    "failed": 2
  },
  "security": {
    "vulnerable": 2,
    "defended": 5,
    "inconclusive": 1
  }
}
```

人工答案评审尚未完成。受控故障与真实服务错误分列；真实模型不自评。HTTP确认时间为本进程ASGI接口测量，不是公网或TCP性能；没有TTFT。
