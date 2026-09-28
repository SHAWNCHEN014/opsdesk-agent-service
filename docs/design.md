# Design decisions

## User outcomes

1. Explain an IT procedure, with evidence and no unnecessary ticket.
2. Record a personal fault and hand it to an engineer.
3. Identify widespread service impact, create a work order and record an escalation.
4. Ask an external assistant about progress after an engineer update.

## Runtime

An execution graph coordinates named agent nodes with explicit dependencies. Intake, evidence retrieval and history recall run concurrently. Priority assessment consumes intake. Advice generation consumes priority/evidence/history. Review evaluates the final generated answer. Each node emits timestamped events and typed results, with bounded model calls and transparent demo/fallback status. No independent-model or fully autonomous-production claim is made.

A request gateway owns identity, input sanitization, user-scoped threads, idempotency, persistence, SSE progress and operation outcomes. Completed non-FAQ requests schedule durable actions. Internal MCP tools perform work-order creation, Excel export and notification recording. Actions have dependency IDs, leases, retries, dead-letter states and an audit log; handlers deduplicate side effects.

External MCP tools expose assistance and authorized operation status. A simulated Alexa+ web mode calls a real HTTP MCP client through the authenticated backend. It is not an official Alexa+ integration. Local demonstration authentication does not claim enterprise SSO.

## Retrieval and memory

IT Markdown/PDF/text is segmented into SQL-backed evidence. Lexical BM25 ranking and optional Chroma/Ollama vector ranking are fused with reciprocal ranks, then reranked using query affinity. Vector provenance includes the embedding model identity; mismatches require rebuild. Redis caches a user-scoped thread history; SQL is the persistent fallback. Older turns are summarized and recent messages retained.

## Local isolation

New app: 8085. New Compose database and Redis use their own services/volumes. Runtime files are under var/; evaluation outputs under artifacts/. No live prototype data is reused. Default notifications are records, not outbound email.
