# Implementation record

Started: 2026-09-28, in the initially empty Desktop/OpsDesk directory.

This implementation is authored from the user's IT service-desk requirements and official library documentation. An earlier MindBridge-based prototype was inspected in a provenance audit and is not the implementation baseline. We do not claim a legally isolated clean-room process: the authoring assistant had seen the earlier source during that audit. No earlier project code, prompts, Skills, UI assets, tests or evaluation data are to be copied into this repository.

The new design uses durable support requests, a dependency graph of typed agent nodes, final-answer review, and a separate action queue. It does not use the earlier claim/blackboard/decide-act implementation.

Requirements: FAQ without a ticket; personal fault with a work order; widespread outage with escalation record; engineer follow-up; retrieval evidence; history; Skills; model and infrastructure observability; idempotent external requests; executable MCP Streamable HTTP tools and a clearly labelled simulated Alexa+ UI.

All demonstration identities, knowledge and evaluation cases are synthetic. Model weights and third-party libraries are downloaded from their own providers and retain their licenses. Keep real timestamps, source hashes, test outputs and the final comparison audit. A similarity score alone is not a legal clearance.

Competition status: formally submitted on 2026-09-28 to Build, Ship, Shape: Amazon Developer Hackathon, Alexa+ track. Devpost confirmed successful submission before participation wording was added to the resume. See [submission record](submission-record.md); no award or finalist status is claimed.
