# OpsDesk — evidence-backed IT support

OpsDesk turns an employee's IT question into a reviewed answer and, when needed, a traceable work order. It connects a web workspace and a **clearly labelled simulated Alexa+ assistant** to the same support workflow through real MCP tools.

**Status:** independently reimplemented starting 28 September 2026; hackathon preparation, not yet submitted. Notifications are recorded locally. Demo guidance and identities are fictional.

![Actual simulated-assistant workflow with English model response and MCP protocol](docs/images/mcp-workflow.png)

## What works

- Knowledge questions return document evidence without creating tickets.
- Personal incidents and service requests queue P2 work orders; genuine widespread incidents queue P1 escalation records.
- A dependency graph coordinates intake, retrieval, history, priority, drafting and final-answer review. Four roles call the same local Ollama model in real-model mode. The retrieval and history nodes use tools, without separate model calls.
- SQL stores requests, conversations, work orders and action jobs. Redis caches user-scoped history; recent turns and a bounded extractive history summary are supplied to the response agent.
- Chroma vectors and bilingual BM25 rankings are combined using reciprocal ranks and query-affinity reranking. Embedding model identity and document segment IDs are checked before an index is reused.
- Internal MCP stdio tools create work orders, append an Excel ledger and record escalations. Durable jobs have dependencies, leases, backoff, a retry budget, dead letters and audit records.
- Engineers record investigation and resolution. Revision checks reject stale edits. External MCP status calls show the owner's latest ticket updates.
- Web SSE exposes progress and reviewed answer chunks. The answer is buffered for review; these are **display chunks**, not raw model-token streaming.

```mermaid
flowchart LR
 W[Web workspace / SSE] --> G[Authenticated request gateway]
 A[Simulated assistant] --> H[MCP Streamable HTTP]
 H --> G
 G --> I[Intake]
 G --> E[Evidence: BM25 + Chroma]
 G --> M[History: Redis + SQL]
 I --> P[Impact priority]
 P --> D[Response draft]
 E --> D
 M --> D
 D --> R[Final answer review]
 R --> Q[SQL action queue]
 Q --> T[MCP stdio tools]
 T --> C[Work order / Excel / escalation receipt]
```

## Quick start — no model download required

Python 3.12 and Docker Compose are supported. From this repository:

```bash
docker compose --env-file .env.example up --build -d
```

Open **http://127.0.0.1:8085/**. The explicit example file selects deterministic **demo mode**. This mode does not call an LLM or build vectors.

| Role | Username | Local demo password |
| --- | --- | --- |
| Employee | employee | local-demo-only |
| Engineer | engineer | engineer-demo-only |

New Compose services use MySQL port 13308, Redis port 16381 and dedicated `opsdesk-independent` volumes. Runtime artefacts are excluded from Git. Use one API worker for this demonstration: active model operations are in-process, while queued business actions are durable.

## Real Ollama + MySQL + Redis + Chroma

Install Ollama from its official provider, then install the models:

```bash
ollama pull qwen3:8b
ollama pull nomic-embed-text-v2-moe
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
docker compose --env-file .env.example up -d mysql redis
cp .env.example .env
```

Set these fields in `.env`:

```dotenv
OPSDESK_DATABASE_URL=mysql+pymysql://opsdesk:local-database-demo@127.0.0.1:13308/opsdesk?charset=utf8mb4
OPSDESK_REDIS_URL=redis://127.0.0.1:16381/0
OPSDESK_MODEL_MODE=ollama
OPSDESK_VECTOR_SEARCH=true
```

Run the native API against the containerised database/cache:

```bash
.venv/bin/uvicorn opsdesk.main:app --host 127.0.0.1 --port 8085
```

Log in as the engineer → **Operations / 运行与知识** → **Rebuild vector index / 重建向量索引**. The index must say Ready before testing hybrid retrieval. Real model calls can take tens of seconds on local hardware. Failed model roles use explicit fallbacks recorded in the outcome. Missing vector service falls back to lexical retrieval; a successful demo-mode run is not evidence that the full model stack works.

Do not run the Compose web service and native API on port 8085 simultaneously. Existing seed passwords stay as initially configured. This demonstration uses local accounts and cookies, not enterprise SSO or OAuth.

## Try the workflow

1. Employee: `How do I request access to a business system?` → FAQ / P3, document evidence, no ticket.
2. Employee: `My laptop cannot turn on. Only I am affected.` → INCIDENT / P2, queued work order and Excel export.
3. Select **Simulated Alexa+ assistant / MCP**, then send `All employees cannot access the core business system. The service is unavailable.` → INCIDENT / P1; the interface displays negotiated MCP protocol 2025-11-25.
4. Engineer: open Work orders, enter an investigation note, then a verified resolution. Open Operations to inspect MCP execution audits, escalation receipts and download the workbook.

The simulation is a web text interface to actual support/status tools. It does not use an official Alexa SDK, device, Amazon-hosted service or AWS runtime.

## MCP interfaces

The authenticated HTTP endpoint is `/mcp/`, implementing MCP **2025-11-25** over Streamable HTTP. Tools: `support_request(message, request_id, thread_id?)` and `request_status(operation_id)`. HTTP cookies identify the signed-in user; the configured local bearer demo token maps to the demo employee. Tools never accept a caller-supplied owner ID. A request ID can be replayed for identical input; conflicting input returns an error.

Internal action tools run separately using `python -m opsdesk.action_server` over stdio. They accept persisted operation IDs and validate eligibility. There is no arbitrary shell-execution tool. The default notification mode is `record`; SMTP must be explicitly configured. SMTP can duplicate delivery if the process dies after sending and before receipt commit, so this project does not claim exactly-once email delivery.

## Verification

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/verify_live.py --require-real
.venv/bin/python scripts/evaluate.py
```

The live verifier checks real model-role success, vector evidence, MySQL, Redis history hits, HTTP MCP negotiation, internal MCP audits, idempotent requests, work orders, workbook download, escalation recording and engineer updates visible through MCP. Synthetic evaluation is a small authored regression set, not a production accuracy claim. See [verification report](docs/verification.md) for measured results and limits.

## Source, licence and development

This implementation was authored from abstract IT requirements and official library interfaces. Earlier prototype source had been inspected during an audit; a legally isolated clean-room process is not claimed. Its code, prompts, corpus, UI, Skills and evaluation data were not copied into this implementation. The new design uses a dependency graph and durable support operations rather than the prototype's claim/blackboard runtime. The post-implementation comparison is documented in [source review](docs/source-review.md).

New code is MIT licensed. Keep [third-party notices](THIRD_PARTY_NOTICES.md) and archived dependency licences. Model weights and images are obtained separately from their upstream providers.

Official interface references: [Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk), [MCP HTTP transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports), [Ollama chat](https://docs.ollama.com/api/chat), [Ollama embeddings](https://docs.ollama.com/api/embed), [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/).

[中文逐步验收](docs/testing-zh.md) · [Technical design](docs/design.md) · [English submission draft](docs/submission.md)
