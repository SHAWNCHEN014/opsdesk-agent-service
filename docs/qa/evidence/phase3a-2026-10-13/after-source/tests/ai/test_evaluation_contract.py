"""Offline evaluator contracts; no model/vector service is exercised here."""
from copy import deepcopy
from pathlib import Path
import socket

import pytest

from scripts.qa.ai_metrics import load_dataset, latency_summary, profile_gate, retrieval_grade, retrieval_summary, trace_errors, fault_observation
from scripts.qa.real_ai import local_only


def test_rank_metrics_and_no_answer_are_not_answer_accuracy():
    case = {"expected_sources": ["current"], "forbidden_top1": ["retired"]}
    grade = retrieval_grade(case, [{"source": "noise"}, {"source": "current"}])
    assert grade["rr"] == .5 and grade["hit"] and grade["source_recall"] == 1
    assert grade["precision_at_k"] == .25
    assert retrieval_grade(case, [{"source": "retired"}, {"source": "current"}])["status"] == "failed"
    assert retrieval_grade({"expected_sources": []}, [{"source": "noise"}])["status"] == "inconclusive"
    assert retrieval_grade(case, [{"source": "noise"}])["status"] == "failed"
    summary = retrieval_summary([{"mode": "hybrid", "grade": grade},
        {"mode": "hybrid", "grade": retrieval_grade({"expected_sources": []}, [])}])["hybrid"]
    assert summary["queries"] == 2 and summary["positive_queries"] == 1 and summary["mrr_at_4"] == .5


@pytest.mark.parametrize("fault,code", [("retrieval-pass", 0), ("retrieval-miss", 1), ("environment", 2),
    ("execution", 2), ("empty", 2), ("human", 2), ("workflow", 1), ("vulnerable", 1)])
def test_real_profile_exit_contract(fault, code):
    result = {"retrieval": [{"grade": {"status": "passed"}}], "agent": []}
    if fault == "retrieval-miss": result["retrieval"][0]["grade"]["status"] = "failed"
    if fault in {"environment", "execution"}: result[fault+"_error"] = "ControlledError"
    if fault == "empty": result["retrieval"] = []
    if fault in {"human", "workflow", "vulnerable"}:
        result["agent"] = [{"deterministic_result": "failed" if fault == "workflow" else "passed",
                            "security_result": "vulnerable" if fault == "vulnerable" else "inconclusive"}]
    assert profile_gate(result)["exit_code"] == code


def test_gold_validation_detects_tampering_and_dangling_source(tmp_path):
    from hashlib import sha256
    import json
    root = Path(__file__).resolve().parents[2] / "evaluation/real_ai/v1"
    data, manifest = load_dataset(root)
    assert len(data["rag_cases"]) == 28 and data["synthetic_only"]
    import shutil
    shutil.copytree(root, tmp_path / "set"); root = tmp_path / "set"
    (root / "knowledge/vpn.md").write_text("tampered")
    with pytest.raises(ValueError, match="hash"): load_dataset(root)
    manifest["files"]["knowledge/vpn.md"] = sha256((root / "knowledge/vpn.md").read_bytes()).hexdigest()
    data["rag_cases"][0]["expected_sources"] = ["absent.md"]
    (root / "cases.json").write_text(json.dumps(data))
    manifest["files"]["cases.json"] = sha256((root / "cases.json").read_bytes()).hexdigest()
    (root / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="absent"): load_dataset(root)


def test_trace_order_duplicates_and_missing_nodes_are_detected():
    names = ["intake", "evidence", "recall", "priority", "draft", "review"]
    events = [{"node": name, "phase": phase} for name in names for phase in ["started", "complete"]]
    assert not trace_errors(events)
    assert "missing_node" in trace_errors(events[:-1])
    assert "duplicate_or_dependency_order" in trace_errors(events[6:8]+events)


def test_local_guard_denies_cloud_connections_and_restores_socket():
    original = socket.socket.connect
    with local_only(11434), socket.socket() as client:
        with pytest.raises(RuntimeError, match="only permits"): client.connect(("198.51.100.1", 443))
        with pytest.raises(RuntimeError, match="only permits"): client.connect(("127.0.0.1", 80))
    assert socket.socket.connect is original
    assert latency_summary([])["n"] == 0
    summary = latency_summary([50, 10, 30]); assert summary["p50_ms"] == 30 and summary["p95_ms"] == 50


@pytest.mark.parametrize("calls,status", [([], "not_run"), ([{"provider": "controlled_fault"}], "exercised")])
def test_unexercised_fault_is_not_a_success_or_product_failure(calls, status):
    assert fault_observation("review_timeout", calls)["status"] == status


def test_hybrid_cannot_claim_pass_after_silent_lexical_fallback(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from opsdesk import retrieval
    from scripts.qa.real_ai import rag_suite
    observed, recorded = [], []
    async def embed(*args):
        observed.append({"kind": "embedding", "success": True}); return [[1, 0]]
    class Collection:
        def query(self, **kwargs):
            observed.append({"kind": "chroma_query", "success": True})
            return {"ids": [["segment"]], "distances": [[0]]}
    class Index:
        config = None
        collection = Collection()
        vector_state = {"ready": True}
        def rows(self): return [SimpleNamespace(id="segment", source="vpn.md", title="VPN", text="Synthetic guidance")]
        def lexical(self, *args): return [("segment", 1)]
        async def search(self, *args): return []  # Silent BM25-only implementation.
    monkeypatch.setattr(retrieval, "embed", embed)
    data = {"rag_cases": [{"case_id": "fallback", "user_input": "VPN", "expected_sources": ["vpn.md"]}]}
    with pytest.raises(RuntimeError, match="not a hybrid pass"):
        asyncio.run(rag_suite(Index(), data, observed, recorded.append))
    assert [r["records"][0]["mode"] for r in recorded] == ["bm25", "vector"]
