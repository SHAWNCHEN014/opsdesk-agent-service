"""QA-GATE-01: subprocess exit status and machine report, isolated in tmp_path.

The PROJECT adapter also works on the original script: its fixed output path
must never overwrite a historical report during the red (pre-fix) run.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[2]
BASELINE = REPO / "evaluation/cases.json"


def run_evaluator(tmp_path, cases, args=(), config=None, fault=None):
    (tmp_path / "evaluation").mkdir()
    case_path = tmp_path / "evaluation/cases.json"
    if cases is not None:
        case_path.write_text(cases if isinstance(cases, str) else json.dumps(cases, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "artifacts/evaluation.json"
    env = {key: value for key, value in os.environ.items() if not key.startswith("OPSDESK_")}
    env.update(PYTHONPATH=str(REPO), PYTHONDONTWRITEBYTECODE="1", OPSDESK_DATABASE_URL="sqlite:///" + str(tmp_path / "eval.db"),
        OPSDESK_MODEL_MODE="demo", OPSDESK_VECTOR_SEARCH="false", OPSDESK_REDIS_URL="", OPSDESK_WORKER_ENABLED="false",
        OPSDESK_LEDGER_FILE=str(tmp_path / "ledger.xlsx"), OPSDESK_VECTOR_DIRECTORY=str(tmp_path / "vectors"))
    env.update(config or {})
    wrapper = """
import asyncio, runpy, sys
from pathlib import Path
script, root, fault = sys.argv[1:4]
sys.argv = [script] + sys.argv[4:]
namespace = runpy.run_path(script, run_name='isolated_evaluator')
namespace['main'].__globals__['PROJECT'] = Path(root)
if fault == 'vector-unavailable':
    async def unavailable(self):
        self.vector_state.update(ready=False, error='Synthetic index unavailable')
    namespace['KnowledgeIndex'].restore_vectors = unavailable
if fault == 'vector-degraded':
    async def ready(self):
        self.vector_state.update(ready=True, embedding_identity='synthetic')
    async def identity(config):
        return 'synthetic'
    async def unavailable_embed(config, texts):
        raise TimeoutError('Synthetic embedding timeout')
    retrieval_globals = namespace['KnowledgeIndex'].search.__globals__
    retrieval_globals['embedding_identity'] = identity
    retrieval_globals['embed'] = unavailable_embed
    namespace['KnowledgeIndex'].restore_vectors = ready
if fault == 'query-failure':
    async def broken(self, query, limit=4):
        raise RuntimeError('Synthetic retrieval failure')
    namespace['KnowledgeIndex'].search = broken
raise SystemExit(asyncio.run(namespace['main']()))
"""
    process = subprocess.run([sys.executable, "-c", wrapper, str(REPO / "scripts/evaluate.py"), str(tmp_path), fault or "none",
        "--cases", str(case_path), "--output", str(output), *args], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    report = json.loads(output.read_text()) if output.exists() else None
    return process, report


def baseline_cases():
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def test_baseline_gate_passes_with_all_original_samples(tmp_path):
    process, report = run_evaluator(tmp_path, baseline_cases())
    assert process.returncode == 0, process.stderr
    assert report["status"] == "passed" and report["gate"]["passed"]
    assert report["classification_size"] == report["intent_correct"] == report["priority_correct"] == 24
    assert report["retrieval_size"] == 12 and report["hit_at_4"] == 1
    assert report["mrr"] == pytest.approx(17 / 18)
    assert report["vector_queries"] == 0 and report["profile"] == "bm25"
    assert report["dataset_sha256"] and report["gate"]["criteria"]["min_mrr"] == .9


@pytest.mark.parametrize("fault", ["intent", "priority", "retrieval", "mrr"], ids=["intent-mismatch", "priority-mismatch", "retrieval-miss", "rank-threshold"])
def test_completed_but_failing_evaluation_returns_one(tmp_path, fault):
    cases = baseline_cases()
    args = ()
    if fault == "intent":
        cases["classification"][0][1] = "INCIDENT"
    elif fault == "priority":
        cases["classification"][0][2] = "P1"
    elif fault == "retrieval":
        cases["retrieval"][0][0] = "zzzznevermatchingterm"
    else:
        args = ("--min-mrr", "1")
    process, report = run_evaluator(tmp_path, cases, args)
    assert process.returncode == 1, process.stdout + process.stderr
    assert report["status"] == "failed" and not report["gate"]["passed"]
    assert report["gate"]["failures"]


@pytest.mark.parametrize("cases", [
    None, "not-json", {"classification": [], "retrieval": []},
    {"classification": [["hello", "INVALID", "P3"]], "retrieval": [["VPN", "connectivity.md"]]},
    {"classification": [["hello", "FAQ"]], "retrieval": [["VPN", "connectivity.md"]]},
], ids=["missing-file", "bad-json", "empty-dataset", "invalid-label", "malformed-row"])
def test_invalid_or_missing_input_returns_incomplete(tmp_path, cases):
    process, report = run_evaluator(tmp_path, cases)
    assert process.returncode == 2, process.stdout + process.stderr
    assert report["status"] == "error" and not report["gate"]["passed"]
    assert report["errors"] and "intent_correct" not in report


@pytest.mark.parametrize("args", [("--min-mrr", "nan"), ("--min-hit-at-4", "1.1")], ids=["nan-threshold", "out-of-range"])
def test_invalid_threshold_cannot_pass(tmp_path, args):
    process, _ = run_evaluator(tmp_path, baseline_cases(), args)
    assert process.returncode == 2


@pytest.mark.parametrize("config,fault", [
    ({"OPSDESK_MODEL_MODE": "invalid-mode"}, None),
    ({"OPSDESK_KNOWLEDGE_DIRECTORY": "missing-knowledge"}, None),
    ({"OPSDESK_VECTOR_SEARCH": "true"}, "vector-unavailable"),
    ({"OPSDESK_VECTOR_SEARCH": "true"}, "vector-degraded"),
    ({}, "query-failure"),
], ids=["bad-config", "missing-corpus", "required-vectors-unavailable", "hybrid-degraded-to-bm25", "retrieval-exception"])
def test_cannot_complete_evaluation_is_not_a_pass(tmp_path, config, fault):
    process, report = run_evaluator(tmp_path, baseline_cases(), config=config, fault=fault)
    assert process.returncode == 2, process.stdout + process.stderr
    assert report["status"] == "error" and not report["gate"]["passed"]
    assert report["errors"]


def test_report_write_failure_cannot_return_success(tmp_path):
    blocked_output = tmp_path / "output-is-a-directory"
    blocked_output.mkdir()
    process, report = run_evaluator(tmp_path, baseline_cases(), args=("--output", str(blocked_output)))
    assert process.returncode == 2, process.stdout + process.stderr
    summary = json.loads(process.stdout.splitlines()[-1])
    assert summary["status"] == "error" and not summary["gate"]["passed"]
    assert summary["errors"][0]["stage"] == "report"
    assert report is None
