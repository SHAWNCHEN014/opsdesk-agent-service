# Developer feedback and friction log

Recorded during the independent OpsDesk implementation on 28 September 2026. These are observed integration lessons from a local demonstration, not production measurements or claims of defects in the upstream products. No official Alexa device, Alexa SDK or AWS service was tested.

## 1. MCP tool result representation

- **Task:** Consume a dictionary result from an MCP Python SDK tool and display its request or action state.
- **Steps:** Discover the tools, call a tool, and inspect its returned content in the client.
- **Expected:** The client could obtain the result as structured content.
- **Observed:** The result could arrive as JSON inside a text content block; a structured-content-only consumer missed it.
- **Severity:** Important for interoperability.
- **Workaround:** Prefer structured content when present; otherwise decode a JSON text content block and validate the expected result shape.
- **Suggestion:** Include both return formats and a small compatibility example in onboarding documentation. This is an interoperability requirement, not a demonstrated SDK defect.

## 2. Public origin versus internal MCP address

- **Task:** Run the browser API and the simulated assistant's MCP client inside a Docker deployment with a mapped host port.
- **Steps:** Build the API image, map its port, log in from the browser, and submit through the simulated assistant.
- **Expected:** Browser-origin checks and the server's internal MCP connection would both succeed.
- **Observed:** Reusing the public browser origin as the internal MCP address did not fit the container network and mapped port.
- **Severity:** Important; blocked that deployment configuration.
- **Workaround:** Configure the public origin separately from the internal MCP client URL, then verify the container workflow on host port 8086.
- **Suggestion:** Show separate browser and service-to-service addresses in deployment examples. The original configuration mistake was in this project.

## 3. Procedural question versus operational incident

- **Task:** Answer the English procedure question “How do I request access” without creating a work order.
- **Steps:** Submit the question through the real local-model workflow and inspect the intent, priority and action state.
- **Expected:** Knowledge guidance with P3 and no work order.
- **Observed:** The intake model initially treated procedural wording as a service request.
- **Severity:** Important; could create unnecessary work orders.
- **Workaround:** Add a bilingual procedural-question guard to the policy boundary and a regression test. The corrected FAQ workflow passed.
- **Suggestion:** Evaluate procedural and actual-failure pairs explicitly. Do not use a small authored regression set as a production accuracy estimate.

## 4. Conservative final-answer review

- **Task:** Release safe guidance after reviewing the actual final draft.
- **Steps:** Generate an English FAQ answer, run the review role, and inspect the displayed replacement and execution trail.
- **Expected:** Safe, useful original guidance would pass review.
- **Observed:** One safe draft was conservatively rejected and replaced with a visibly marked fallback.
- **Severity:** Important for usefulness; the rejection was exposed rather than hidden.
- **Workaround:** Preserve the review outcome and show a conservative replacement. This remains a known limitation.
- **Suggestion:** Add a larger bilingual review evaluation and calibrate rejection criteria while retaining review of the final generated text.

## Feature request

**Important:** Broader official Alexa+ MCP test-client access with reproducible authenticated request/status examples. It would enable device validation of the currently simulated workplace-support experience. Access and device integration are planned, not completed capabilities.

## Evidence scope

See [verification](verification.md), [implementation record](implementation-record.md) and [design](design.md). Twenty behaviour tests passed; a recorded real-model run covered three synthetic scenarios with MySQL, Redis, Ollama and vector retrieval active. Notifications in the demo are local receipts. The repository is MIT licensed and runnable locally.
