# Submission draft — OpsDesk

Status: prepared locally; not submitted. All links and final eligibility declarations must be completed using the entrant's own accounts.

## Name and tagline

**OpsDesk — IT support with evidence and accountable actions**

An assistant that turns a workplace IT question into reviewed guidance, prioritised work orders and an engineer-visible action trail.

## Inspiration

Employees often describe an IT problem in one sentence, while engineers need its scope, supporting guidance and a usable handoff. We wanted to preserve that simple entry point and make the actions behind an answer visible. The proposed Alexa+ use case is a conversational front door to workplace support. Our demonstration is a clearly labelled web simulation with a real MCP backend.

## What it does

OpsDesk distinguishes procedural questions, service requests and actual incidents. Questions receive evidence without unnecessary tickets. Individual issues queue P2 work orders; widespread incidents queue P1 work orders and escalation receipts. Engineers add investigation and resolution notes. The authenticated status tool returns the owner's latest work-order state.

The simulated assistant submits requests and polls status through MCP Streamable HTTP. The page displays protocol 2025-11-25, processing nodes, evidence and priorities. It does not connect to an official Alexa device or SDK.

## How we built it

The independently authored implementation started on 28 September 2026. FastAPI owns login, user-scoped requests and progress events. A dependency graph coordinates six roles: intake, evidence, recall, priority, drafting and final-answer review. Four roles call the same Qwen3-8B model through Ollama; the evidence and recall nodes use Chroma/BM25 and Redis/SQL respectively.

Final text is reviewed before release. Work orders, Excel export and escalation recording execute through a separate durable SQL queue and internal MCP stdio tools. Jobs have dependencies, leases, bounded retries, dead-letter recovery and audit records. Docker Compose provides isolated MySQL and Redis services; the UI is newly authored HTML, CSS and JavaScript.

We had audited an earlier reference-based prototype before implementation. This repository does not copy its source, prompts, corpus, UI, Skills or tests; it is not described as a legally isolated clean-room process. Newly authored code is MIT licensed and dependency notices are preserved. See the source review and real commit history for evidence.

## Challenges and lessons

- Procedural wording such as “how do I request access” must remain a knowledge question rather than creating a ticket.
- The MCP SDK may return generic dictionaries as JSON text content; consumers must handle that format as well as structured content.
- The assistant's response can finish before queued tools do. We separate answer completion, work-order creation and tool audits in the UI.
- Embedding model or knowledge changes invalidate the vector index. We record its identity and require a rebuild rather than silently mixing vector spaces.
- Engineer updates need concurrency checks and must be visible through the same external status tool.

## Validation and limits

Refer to `docs/verification.md` for actual test counts and runtime evidence. The tested scenarios are synthetic. We make no production user, savings, accuracy uplift or award claims. Escalations are local records in the demonstration, not sent emails. The history summary is bounded and extractive, not an additional summarisation model.

## Accomplishments we are proud of

The complete handoff is inspectable: an employee request passes through evidence retrieval and final-text review, a durable action creates a work order, and an engineer's resolution is visible through the same authenticated MCP status tool. Twenty behaviour tests passed. A recorded real-model run covered three synthetic FAQ, individual-incident and widespread-incident scenarios with MySQL, Redis and vector retrieval active. We also verified the Docker demo separately.

## What we learned

Natural-language classification needs a policy boundary: asking how to request access should not create the same operational action as reporting an actual outage. Answer generation and durable action execution also have different completion states. Exposing those states, evidence sources and review replacements made failures easier to explain. A small synthetic evaluation is useful for finding regressions, but does not establish production accuracy.

## What's next

Validate the conversational flow with an official Alexa+ client when access is available, add enterprise identity integration, expand bilingual retrieval and review evaluations, and harden notification delivery. These are planned improvements, not completed capabilities.

## Product feedback

**MCP Python SDK:** Used for both the external Streamable HTTP interface and internal stdio action tools. Protocol negotiation and tool discovery worked in real runtime tests. Dictionary return formats required a JSON-content fallback in our client. The stateless HTTP server and async lifespan made onboarding practical; we would use it again for interoperable tool interfaces. Access to a broadly available official Alexa+ test client would improve end-to-end device validation.

**Ollama / Qwen:** Used for local structured role outputs and response generation. JSON schemas and disabled thinking made the role boundaries inspectable. Local latency varied by workload, so progress events and explicit fallback records were necessary. We would use it again for a reproducible local demo; performance would need separate production testing.

**Chroma:** Used for persisted embedding retrieval alongside lexical ranking. Model identity and document-ID checks made reuse observable. Index rebuild and service failures need explicit UI status; we would use it again for a small evidence corpus.

**FastAPI, SQLAlchemy, MySQL, Redis, openpyxl, pypdf, Docker Compose:** Used for authenticated APIs, durable records, history caching, workbook export, text extraction and local service isolation. These worked through the tested workflows. Local account auth, a single API worker and text-only PDF extraction are deliberate demo limits, requiring further work for enterprise deployment.

## Submission fields to complete

- Primary track: Alexa+; clearly labelled simulated experience plus real MCP HTTP server.
- Mini challenges: none. No AWS runtime or extra qualifying open-source contribution is claimed.
- GitHub repository URL: https://github.com/SHAWNCHEN014/opsdesk-agent-service
- Public YouTube/Vimeo demo URL: pending upload of the reviewed English-captioned demonstration.
- Entrant and eligibility:本人确认，不能由代码测试代替。
- Final submission confirmation URL/screenshot/time: retain after successful submission; only then update the resume heading to competition participation.
