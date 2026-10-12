"""Small deterministic metrics; these never score open-ended answer correctness."""
from collections import Counter
import json
from pathlib import Path
from hashlib import sha256


def load_dataset(root):
    manifest = json.loads((root / "manifest.json").read_text())
    for name, digest in manifest["files"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Dataset content/hash mismatch")
    data = json.loads((root / "cases.json").read_text())
    if not data.get("synthetic_only") or data.get("top_k") != 4:
        raise ValueError("Synthetic versioned dataset required")
    sources = {p.name for p in (root / "knowledge").glob("*.md")}
    cases = data["rag_cases"] + data["agent_cases"]
    ids = [c["case_id"] for c in cases]
    if not cases or len(set(ids)) != len(ids):
        raise ValueError("Missing/duplicate case IDs")
    for case in cases:
        if not set(case["expected_sources"]) <= sources:
            raise ValueError("Gold source is absent")
    return data, manifest


def retrieval_grade(case, hits, k=4):
    expected = set(case["expected_sources"])
    sources = [h["source"] for h in hits[:k]]
    if not expected:
        return {"status": "inconclusive", "reason": "No unique positive source; candidates require answer-level review",
                "candidate_count": len(sources), "hit": None, "rr": None, "source_recall": None}
    relevant = [i for i, source in enumerate(sources, 1) if source in expected]
    forbidden = bool(sources and sources[0] in case.get("forbidden_top1", []))
    return {"status": "passed" if relevant and not forbidden else "failed", "hit": bool(relevant),
            "rr": 1 / relevant[0] if relevant else 0, "source_recall": len(expected & set(sources)) / len(expected),
            "precision_at_k": sum(source in expected for source in sources) / k,
            "reason": "retired_source_top1" if forbidden else "expected_source_missing" if not relevant else None}


def retrieval_summary(records):
    result = {}
    for mode in sorted({r["mode"] for r in records}):
        rows = [r for r in records if r["mode"] == mode]
        positive = [r["grade"] for r in rows if r["grade"].get("hit") is not None]
        result[mode] = {"queries": len(rows), "positive_queries": len(positive),
            "counts": dict(Counter(r["grade"]["status"] for r in rows)),
            "hit_rate_at_4": sum(g["hit"] for g in positive) / len(positive) if positive else None,
            "mrr_at_4": sum(g["rr"] for g in positive) / len(positive) if positive else None,
            "mean_source_recall_at_4": sum(g["source_recall"] for g in positive) / len(positive) if positive else None}
    return result


def latency_summary(samples):
    samples = sorted(samples)
    if not samples:
        return {"n": 0, "mean_ms": None, "p50_ms": None, "p95_ms": None}
    import math
    return {"n": len(samples), "mean_ms": sum(samples) / len(samples),
            "p50_ms": samples[math.ceil(.50 * len(samples)) - 1],
            "p95_ms": samples[math.ceil(.95 * len(samples)) - 1], "method": "nearest rank; local sequential samples"}


def trace_errors(events):
    completed, started, errors = set(), set(), []
    expected = {"intake": [], "evidence": [], "recall": [], "priority": ["intake"],
                "draft": ["intake", "evidence", "recall", "priority"], "review": ["draft"]}
    for event in events:
        name = event.get("node")
        if name not in expected:
            errors.append("unknown_node"); continue
        if event["phase"] == "started":
            if name in started or not set(expected[name]) <= completed:
                errors.append("duplicate_or_dependency_order")
            started.add(name)
        elif event["phase"] == "complete":
            if name in completed or name not in started:
                errors.append("duplicate_or_unstarted_completion")
            completed.add(name)
    if completed != set(expected): errors.append("missing_node")
    return errors


def fault_observation(fault, calls):
    if fault not in {"review_timeout", "intake_malformed"}:
        return None
    exercised = any(c.get("provider") == "controlled_fault" for c in calls)
    return {"requested": fault, "status": "exercised" if exercised else "not_run",
            "reason": None if exercised else "Earlier guard bypassed the requested model branch; no fault coverage claimed"}


def profile_gate(report):
    if report.get("environment_error") or report.get("execution_error"):
        return {"exit_code": 2, "status": "incomplete", "reason": "precondition_or_execution_incomplete"}
    grades = [r["grade"]["status"] for r in report["retrieval"]]
    deterministic = [r["deterministic_result"] for r in report["agent"]]
    if "failed" in grades or "failed" in deterministic or any(r.get("security_result") == "vulnerable" for r in report["agent"]):
        return {"exit_code": 1, "status": "failed", "reason": "recorded_deterministic_findings"}
    if report["agent"]:
        return {"exit_code": 2, "status": "incomplete", "reason": "independent_human_answer_review_pending"}
    if not report["retrieval"]:
        return {"exit_code": 2, "status": "incomplete", "reason": "no_cases_executed"}
    return {"exit_code": 0, "status": "passed", "reason": "positive_source_retrieval_only; ambiguous/no-answer semantics unapproved"}
