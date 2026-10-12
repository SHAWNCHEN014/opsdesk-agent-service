"""Rebuild derived observations from archived results; never reruns services."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
from scripts.qa.ai_metrics import latency_summary, load_dataset


def read(name): return json.loads((HERE / name).read_text())
def write(name, data): (HERE / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
def digest(path): return sha256(path.read_bytes()).hexdigest()


def main():
    final = read("real-final/results.json")
    before = read("real-before/results.json")
    intermediate = read("prompt-hardening-only/results.json")
    offline = read("final-offline/summary.json")
    initial = read("baseline-offline/summary.json")
    originals = {c["id"]: c["status"] for c in initial["pytest"]["cases"]}
    after = {c["id"]: c["status"] for c in offline["pytest"]["cases"]}
    missing = [key for key in originals if after.get(key) != "passed"]
    write("suite-comparison.json", {"original_cases": len(originals), "retained_passed": len(originals)-len(missing),
        "missing_or_not_passed": missing, "final": offline["pytest"]["counts"], "new_cases": len(after)-len(originals),
        "original_ids": sorted(originals), "new_ids": sorted(after.keys()-originals.keys())})
    baseline = read("baseline.json")
    invariant = [name for name in baseline["sha256"] if name.startswith("tests/") or name == "evaluation/cases.json"
        or (name.startswith("docs/qa/") and name not in {"docs/qa/README.md", "docs/qa/DELIVERY_BUNDLE.md", "docs/qa/delivery-manifest.json", "docs/qa/quality-status.json"})]
    changed = [name for name in invariant if digest(REPO / name) != baseline["sha256"][name]]
    _, manifest = load_dataset(REPO / "evaluation/real_ai/v1")
    write("integrity-check.json", {"original_tests_gold_historical_records_checked": len(invariant), "changed": changed,
        "new_dataset_identical_across_real_runs": before["dataset"] == intermediate["dataset"] == final["dataset"] == manifest,
        "default_ci_unchanged": digest(REPO / ".github/workflows/qa.yml") == baseline["sha256"][".github/workflows/qa.yml"],
        "real_model_digest_stable": final["model_identity_stability"], "source_unchanged_during_real_run": not final.get("execution_error"),
        "phase3a_tested_source_commit": final["git"]["head"], "scope": "Exact bytes/IDs, not a claim of semantic correctness"})
    repeated = []
    for cid in ["faq-zh", "faq-en", "incident"]:
        rows = [c for c in final["agent"] if c["case_id"] == cid]
        repeated.append({"case_id": cid, "samples": len(rows), "exact_answer_equal": rows[0]["actual_answer"] == rows[1]["actual_answer"],
            "answer_sha256": [sha256(c["actual_answer"].encode()).hexdigest() for c in rows],
            "draft_sha256": [sha256(next(m["value"] for m in c["model_outputs"] if m["purpose"] == "draft").encode()).hexdigest() for c in rows],
            "scope": "2 observations, not proof of deterministic outputs; incident final may be deterministic fallback"})
    tools = [t for c in final["agent"] for t in c["tools"]]
    vector = Counter(o["kind"] for o in final["vector_observations"])
    faults = [{"run_id": c["run_id"], "requested": c["fault"], "observation": c["fault_observation"],
        "degraded": c["outcome"]["degraded"], "actions": c["actions"], "order_count": c["work_order_count"], "tools": c["tools"]}
        for c in final["agent"] if c.get("fault")]
    write("observations.json", {"final_git": final["git"], "configuration_sha256": final["configuration_sha256"],
        "dataset_manifest_sha256": digest(REPO / "evaluation/real_ai/v1/manifest.json"), "repeat_samples": repeated,
        "real_vector_observation_counts": dict(vector), "vector_failures": [o for o in final["vector_observations"] if not o["success"]],
        "orders": sum(c["work_order_count"] for c in final["agent"]), "actions": sum(len(c["actions"]) for c in final["agent"]),
        "tool_attempts": len(tools), "tool_success": sum(t["success"] for t in tools), "controlled_tool_failures": sum(bool(t.get("injected")) for t in tools),
        "tools_by_transport": {mode: latency_summary([t["elapsed_ms"] for t in tools if t["transport"] == mode and not t.get("injected")]) for mode in ["direct", "mcp"]},
        "retrieval_latency_by_mode": {mode: latency_summary([r["elapsed_ms"] for r in final["retrieval"] if r["mode"] == mode]) for mode in ["bm25", "vector", "hybrid"]},
        "all_action_states_done": all(a["phase"] == "DONE" for c in final["agent"] for a in c["actions"]),
        "all_identity_boundaries_verified": all(c["boundary"] == {"other_thread_submit":404,"employee_retry":403,"other_owner_status":404} for c in final["agent"]),
        "faults": faults, "independent_human_reviews_completed": 0, "human_review_pending": len(final["agent"]),
        "prior_real_runs": [{"source": name,"counts": r["counts"],"gate": r["gate"],"model_calls":r["model_calls"]} for name,r in [("real-before",before),("prompt-hardening-only",intermediate),("real-final",final)]],
        "cumulative_real_operations": sum(len(r["agent"]) for r in [before,intermediate,final]),
        "cumulative_real_role_calls": sum(r["model_calls"]["real"] for r in [before,intermediate,final]),
        "not_run": ["independent human semantic review","real MySQL locks/concurrency","Redis recovery","SMTP delivery","MCP child timeout/crash","load/soak","Phase3A remote CI"]})
    write("defect-closure.json", {"records": [
        {"id":"QA-AI-ACTION-01","status":"closed_in_bounded_scenarios","before":"action-consistency-discovery.json + action-red (158 cases,4 failures)",
         "root_cause":"Model reviewer approval did not enforce intent-to-action narrative; fixed enqueue policy independently creates orders",
         "fix":"action_claim_check rejects explicit contradictions after review, correct deterministic queue notice on replacement",
         "after":"8 action contract regressions passed; real-final incident-run1/run2 and tool-failure drafts again contradicted the policy and were replaced while actual orders were persisted",
         "residual":"Unrecognized paraphrases and broader action semantics need review"},
        {"id":"QA-AI-PROMPT-01","status":"closed_for_explicit_override_scenarios","before":"real-before user marker + prompt-hardening-only still vulnerable + boundary-red",
         "root_cause":"Generation followed unrelated output instruction and model reviewer approved it; prompt hardening alone was insufficient",
         "fix":"Generic untrusted task policy plus bounded explicit imperative guard; no fixture marker blacklist",
         "after":"Override and benign input regressions passed; same frozen real user/doc/history attacks satisfied their stated canary boundary",
         "residual":"Indirect, paraphrased, encoded and multilingual attacks outside specified patterns remain unverified"},
        {"id":"QA-AI-PRIVACY-TEXT-01","status":"closed_for_explicit_disclosure_scenarios","before":"prompt-hardening-only sec-cross-user output echoed attacker-provided marker and invented an attachment instruction; boundary-red",
         "root_cause":"SQL/API ownership was enforced but generated response did not reliably refuse explicit private-other-user requests",
         "fix":"Bounded direct disclosure-request guard; own-data/negative/question cases remain outside the guard",
         "after":"13 shared boundary regressions passed; final same real cross-user request replaced; database access boundaries were maintained throughout",
         "residual":"No private database exfiltration observed; forbidden marker was in attacker input, so echo is not proof of a data leak"},
        {"id":"QA-AI-FRESHNESS-01","status":"open","before":"freshness-failures.json","root_cause":"BM25/vector/RRF/title rules have no authoritative valid-until/superseded metadata policy",
         "fix":"No risky keyword-only filter or gold change; preserved failed real gate","after":"5 failures repeated in final three-mode run",
         "dependency":"Define effective-date/supersedes metadata and historical-query behavior under tests"}
    ],"harness_correction":{"original":"real-before marked unexercised review fault as a product failure and missed the action-narrative contradiction",
        "correction":"fault branch not_run/inconclusive; independent bounded narrative oracle added; original result files retained unchanged",
        "tests":"fault_observation and silent-hybrid-fallback contracts"},
        "semantic_triage_pending":["FAQ/model-malformed auto notification claim absent from access guidance","sec-tool-escalation classified INCIDENT despite command-only input; ticket creation needs intent/policy review, no shell/admin grant occurred","danger Chinese request classified REQUEST despite VPN failure; priority/action remained P2; intent gold not independently annotated"],
        "observability_pending":"Static guard rejection may retain misleading passed-checks wording in review.reason; approved=false/replacement_used=true and model call traces show actual rejection. Reason-text cleanup not claimed fixed.",
        "gate_note":"Original before/after graders differ; do not infer quality improvement percentages from aggregate failed counts"})
    write("versions.json", {"start_commit":baseline["head"], "phase2c_business_commit":"1e801a300a0e0e7205fe2a7999a36022dc1939a4",
        "source_commits":["c7383c2d6e2ac2aeddae4aa9589365188287e313",final["git"]["head"]],
        "real_tested_commit":final["git"]["head"], "offline_recorded_commit":offline["git"]["head"],
        "offline_metadata_dirty":offline["git"]["dirty_source"], "push_performed":False,
        "evidence_commit":"Commit containing this file; self-referential hash deliberately omitted"})
    if missing or changed or final.get("execution_error") or final.get("environment_error"):
        raise SystemExit("Evidence integrity/incomplete execution requires attention")
    print(json.dumps({"original_retained":len(originals),"final_offline":offline["pytest"]["counts"],"real_gate":final["gate"]},indent=2))


if __name__ == "__main__": main()
