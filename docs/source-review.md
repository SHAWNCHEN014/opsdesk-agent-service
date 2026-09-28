# Post-implementation source review

The new implementation began in an empty directory on 28 September 2026. The initial design was committed before the runtime was implemented. Its new dependency graph, durable service-request model, final-output review, cookie sessions, dual MCP transports, work-order lifecycle and UI were authored from abstract requirements and official library APIs.

Earlier MindBridge/prototype source was seen in a prior audit. That exposure is disclosed; a legally isolated clean-room process is not claimed. Earlier code, prompts, Skills, guidance documents, tests, UI assets and evaluation cases were not copied into the new repository.

After the implementation and first end-to-end checks, `scripts/review_origin.py` compared the new source to both reference directories. The initial snapshot found **zero byte-identical files** and **zero exactly matching normalized functions with at least 60 AST nodes**. Identifier and string normalization makes the function comparison sensitive to simple renaming. These are specific tests, not proof that every possible fragment is unrelated.

The highest initial file token similarity was the tiny SVG favicon (0.6326); manual inspection showed shared standard SVG/rectangle syntax, with an independently authored circular O mark versus the reference's M path. The next result was the redaction module (0.4173), whose common email/Chinese-phone patterns were manually reviewed. The new module adds credential/key/private-key handling and uses a different API and pattern set. These files were not modified merely to lower a score.

The comparison excludes dependency/runtime directories and compares selected text-source types. Hashes, paths and methodology are retained in the local reports. Scores are evidence for review, not legal clearance; contracts or independently applicable third-party rights cannot be decided by token similarity.

The root MIT licence covers the newly authored work. Dependency/model/container terms remain separate, as described in `THIRD_PARTY_NOTICES.md`. The earlier restricted prototype and its source archive are not included in the new repository or distribution bundle.
