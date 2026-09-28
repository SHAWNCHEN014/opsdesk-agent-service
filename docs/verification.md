# Verification evidence

Measured on 28 September 2026. These results belong to the independently authored repository, not the earlier prototype.

| Check | Observed result | Scope |
| --- | --- | --- |
| Automated behaviour tests | 20 passed | Auth, origin checks, owner isolation, deduplication/conflicts, bilingual FAQ policy, graph dependencies/concurrency, bounded memory, document import, final draft replacement, leases, retry budget, dead letters, idempotent tools, HTTP MCP and revision conflicts |
| Real-model workflows | FAQ/P3, personal incident/P2, widespread incident/P1 passed | 3 synthetic requests; 12 successful role calls to Qwen3-8B, no role fallback |
| Local measured request durations | 18.420 s / 16.413 s / 27.738 s | One recorded run, not a latency benchmark or service SLA |
| Full infrastructure | MySQL, Redis, Ollama embeddings and Chroma active | Redis history: 2 cache hits, 1 SQL recall, 0 cache errors in the recorded run |
| External MCP | Negotiated 2025-11-25 over Streamable HTTP | Tool discovery, request submission, owned status and engineer resolution visibility |
| Internal MCP | stdio tool execution audited as DONE | Work-order creation, ledger export and local escalation recording |
| Synthetic rule regression | 24/24 intent and 24/24 priority labels | Deterministic fallback only; authored examples, not model/production accuracy |
| Hybrid retrieval regression | 12 queries; HitRate@4 = 1.0, MRR = 0.9583 | All 12 used vectors alongside BM25; small synthetic corpus |
| Dependency inventory | 100 installed distributions, 133 archived licence files | Isolated Python environment; original notices and file hashes retained |
| Docker image workflow | Passed on separate host port 8086 | Demo mode, SQLite test file, internal/external MCP, work-order updates and workbook; separate from the real-model run |

The real workflow verifier also replayed request IDs, verified exactly two tickets for its selected three requests, downloaded the Excel workbook, updated an engineer's ticket through investigation/resolution and checked that the external MCP status tool returned the resolved state. Notification receipts used `record`, not SMTP delivery.

Desktop and narrow-layout browser checks covered login, progress, a simulated MCP incident, ticket history and engineer diagnostics. An English procedure question revealed a model misclassification; the guard was expanded and a regression added. One safe English draft was conservatively rejected by the review model and visibly replaced. This is a known usefulness limitation of the current review fallback, not hidden as a successful original answer.

## Reproduce

- `python -m pytest -q --junitxml=artifacts/unit-tests.xml`
- `python scripts/verify_live.py --require-real --output artifacts/final-live-verification.json`
- `python scripts/evaluate.py`

Artefacts contain synthetic operation IDs and are locally retained under `artifacts/`; a compact public summary is kept here. The unit suite reports one upstream Starlette TestClient deprecation warning; behaviour checks pass.

## Practical limits

This is a local demonstration with seeded identities, a small fictional corpus and a single API process. Pattern-based redaction and final-text checks are not exhaustive security guarantees. There is no enterprise SSO, OCR, official Alexa device integration, AWS runtime, measured cost reduction, production scale test or award claim. History summarisation is bounded extraction. SSE releases reviewed chunks, not raw model tokens. SMTP's crash window prevents an exactly-once delivery claim.
