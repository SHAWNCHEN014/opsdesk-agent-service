from copy import deepcopy
import json
from pathlib import Path
import socket
import xml.etree.ElementTree as ET

import pytest
import yaml

from scripts.qa import offline_guard
from scripts.qa.run_checks import decide_gate, evaluation_result, isolated_environment, junit_result, safe_value


def completed():
    tests = {"status": "completed", "exit_code": 0,
        "counts": {"tests": 109, "passed": 109, "failed": 0, "errors": 0, "skipped": 0},
        "baseline": {"missing_or_duplicate": []}}
    evaluation = {"status": "passed", "exit_code": 0, "gate": {"passed": True}}
    return tests, evaluation, {"status": "completed"}


@pytest.mark.parametrize("fault,expected", [("pass", 0), ("pytest-failed", 1), ("pytest-skipped", 1),
    ("baseline-missing", 1), ("evaluation-failed", 1), ("evaluation-missing", 2),
    ("coverage-missing", 2), ("pytest-interrupted", 2), ("zero-tests", 2), ("blocking-defect", 1)])
def test_quality_gate_cannot_turn_failed_skipped_or_incomplete_into_pass(fault, expected):
    tests, evaluation, coverage = deepcopy(completed())
    if fault == "pytest-failed":
        tests["exit_code"], tests["counts"]["failed"], tests["counts"]["passed"] = 1, 1, 108
    if fault == "pytest-skipped": tests["counts"].update(skipped=1, passed=108)
    if fault == "baseline-missing": tests["baseline"]["missing_or_duplicate"] = ["required case"]
    if fault == "evaluation-failed": evaluation.update(status="failed", exit_code=1, gate={"passed": False})
    if fault == "evaluation-missing": evaluation.update(status="error", exit_code=None)
    if fault == "coverage-missing": coverage["status"] = "error"
    if fault == "pytest-interrupted": tests["exit_code"] = 2
    if fault == "zero-tests": tests["counts"].update(tests=0, passed=0)
    gate = decide_gate(tests, evaluation, coverage, ["tracked defect"] if fault == "blocking-defect" else [])
    assert gate["exit_code"] == expected
    assert gate["status"] == ("passed" if expected == 0 else "failed" if expected == 1 else "incomplete")


def test_junit_counts_setup_errors_skips_and_missing_baseline(tmp_path):
    path = tmp_path / "junit.xml"
    path.write_text('<testsuites><testsuite><testcase classname="a" name="good"/><testcase classname="a" name="bad"><failure/></testcase><testcase classname="a" name="setup"><error/></testcase><testcase classname="a" name="skip"><skipped/></testcase></testsuite></testsuites>')
    result = junit_result(path, 1, ["a::good", "a::absent"])
    assert result["counts"] == {"tests": 4, "passed": 1, "failed": 1, "errors": 1, "skipped": 1}
    assert result["baseline"]["missing_or_duplicate"] == ["a::absent"] and result["baseline"]["passed"] == 1
    path.write_text("not XML")
    with pytest.raises(ET.ParseError): junit_result(path, 0, [])


def test_evaluation_report_missing_rows_is_not_accepted(tmp_path):
    path = tmp_path / "evaluation.json"
    path.write_text(json.dumps({"status": "passed", "classification_size": 24, "retrieval_size": 12}))
    with pytest.raises(ValueError, match="incomplete"): evaluation_result(path, 0)


def test_offline_child_drops_sensitive_environment_and_json_redaction_preserves_structure(tmp_path, monkeypatch):
    for name in ("OPSDESK_DATABASE_URL", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY", "SMTP_PASSWORD", "HTTP_PROXY", "HOME", "COVERAGE_PROCESS_START"):
        monkeypatch.setenv(name, "synthetic-private-secret")
    env = isolated_environment(tmp_path, tmp_path)
    assert "synthetic-private-secret" not in json.dumps(env)
    assert env["OPSDESK_DATABASE_URL"].startswith("sqlite:///") and env["OPSDESK_MODEL_MODE"] == "demo"
    raw = {"error": "password=synthetic-credential Bearer synthetic-token", "values": ["safe", 3]}
    restored = json.loads(json.dumps(safe_value(raw)))
    assert restored["values"] == ["safe", 3]
    assert "synthetic-credential" not in json.dumps(restored) and "synthetic-token" not in json.dumps(restored)


def test_network_guard_blocks_socket_connections_without_sending_data(monkeypatch):
    original = (socket.socket.connect, socket.socket.connect_ex, socket.create_connection)
    try:
        offline_guard.block_network()
        with socket.socket() as client:
            with pytest.raises(RuntimeError, match="disabled"): client.connect(("127.0.0.1", 1))
            with pytest.raises(RuntimeError, match="disabled"): client.connect_ex(("127.0.0.1", 1))
        with pytest.raises(RuntimeError, match="disabled"): socket.create_connection(("127.0.0.1", 1))
    finally:
        socket.socket.connect, socket.socket.connect_ex, socket.create_connection = original


def test_ci_gate_is_required_and_artifacts_are_allowlisted():
    repo = Path(__file__).resolve().parents[2]
    workflow = yaml.load((repo / ".github/workflows/qa.yml").read_text(), Loader=yaml.BaseLoader)
    assert set(workflow["on"]) == {"push", "pull_request", "workflow_dispatch"}
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["offline"]
    assert job["runs-on"] == "ubuntu-24.04" and not job.get("services")
    gate = next(s for s in job["steps"] if s.get("name") == "Run required quality gate")
    assert gate["run"] == "python scripts/qa/run_checks.py --output artifacts/qa/ci"
    assert "continue-on-error" not in gate and "if" not in gate
    upload = job["steps"][-1]
    assert upload["if"] == "always()" and upload["with"]["if-no-files-found"] == "error"
    assert set(upload["with"]["path"].splitlines()) == {"artifacts/qa/ci/" + name for name in
        ("junit.xml", "summary.json", "quality-report.md", "coverage.json", "coverage.xml", "coverage.txt", "evaluation.json", "pytest-output.txt")}
    assert job["steps"][0]["with"]["persist-credentials"] == "false"
    assert all(len(s["uses"].split("@")[1]) == 40 for s in job["steps"] if "uses" in s)
