"""Run the offline quality gate; preserve failures and incomplete results.

python scripts/qa/run_checks.py [--output NEW_DIRECTORY]
Exit 0: complete offline pass; 1: failed checks; 2: incomplete/config error.
Never targets existing data, loads .env, or calls a real model/database.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


REPO = Path(__file__).resolve().parents[2]
DEPENDENCIES = ("pytest", "coverage", "SQLAlchemy", "FastAPI", "httpx", "openpyxl", "mcp", "anyio", "PyMySQL")


def safe_text(value, roots=()):
    # Child environments contain no inherited credentials; redact recognizable
    # credential patterns as an additional measure, including synthetic failures.
    import re
    for root in roots:
        value = value.replace(str(root), "<PATH>")
    value = re.sub(r"(?i)(Bearer\s+)[^\s\"',;<>]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)((?:password|passwd|token|api[_-]?key|secret|cookie)\s*[:=]\s*)[^\s,;<>]+", r"\1[REDACTED]", value)
    return value


def isolated_environment(repo, root):
    # Do not inherit HOME, credentials, proxies, model settings or .env paths.
    env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "WINDIR", "LANG", "LC_ALL") if key in os.environ}
    env.update(PYTHONPATH=str(repo), PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
               TMPDIR=str(root), COVERAGE_FILE=str(root / ".coverage"),
               OPSDESK_DATABASE_URL="sqlite:///" + str(root / "evaluation.db"), OPSDESK_REDIS_URL="",
               OPSDESK_MODEL_MODE="demo", OPSDESK_VECTOR_SEARCH="false", OPSDESK_WORKER_ENABLED="false",
               OPSDESK_ACTION_TRANSPORT="direct", OPSDESK_NOTIFICATION_MODE="record",
               OPSDESK_LEDGER_FILE=str(root / "ledger.xlsx"), OPSDESK_VECTOR_DIRECTORY=str(root / "vectors"),
               OPSDESK_MCP_TOKEN="")
    return env


def safe_value(value, roots=()):
    if isinstance(value, str): return safe_text(value, roots)
    if isinstance(value, list): return [safe_value(item, roots) for item in value]
    if isinstance(value, dict): return {key: safe_value(item, roots) for key, item in value.items()}
    return value


def source_hashes(repo):
    paths = []
    for directory, suffix in (("opsdesk", ".py"), ("tests", ".py"), ("scripts", ".py"),
                              ("knowledge", ".md"), ("skills", ".md"), ("evaluation", ".json")):
        paths.extend((repo / directory).rglob("*" + suffix))
    paths.extend(repo / p for p in ("pyproject.toml", "requirements-dev.txt", "requirements.txt",
        "docs/qa/quality-status.json", "scripts/qa/baseline_cases.json", ".github/workflows/qa.yml") if (repo / p).exists())
    return {p.relative_to(repo).as_posix(): sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def junit_result(path, process_code, required_cases):
    tree = ET.parse(path)
    cases, counts = [], Counter(tests=0, passed=0, failed=0, errors=0, skipped=0)
    for node in tree.findall(".//testcase"):
        name = node.get("classname", "") + "::" + node.get("name", "")
        status = next((state for tag, state in (("failure", "failed"), ("error", "errors"), ("skipped", "skipped")) if node.find(tag) is not None), "passed")
        cases.append({"id": name, "status": status})
        counts["tests"] += 1
        counts[status] += 1
    names = Counter(c["id"] for c in cases)
    return {"status": "completed", "exit_code": process_code, "counts": dict(counts), "cases": cases,
        "baseline": {"required": len(required_cases), "present": sum(names[c] == 1 for c in required_cases),
                     "passed": sum(c["id"] in required_cases and c["status"] == "passed" for c in cases),
                     "missing_or_duplicate": [c for c in required_cases if names[c] != 1]}}


def coverage_result(path):
    raw = json.loads(path.read_text())
    if raw["meta"]["branch_coverage"] is not True:
        raise ValueError("Branch measurement is required")
    totals = raw["totals"]
    if totals["num_statements"] <= 0 or totals["num_branches"] <= 0:
        raise ValueError("Coverage is incomplete")
    return {"status": "completed", "scope": "opsdesk/*.py in Pytest process; model/vector stubs and temporary SQLite",
        "line": {"covered": totals["covered_lines"], "total": totals["num_statements"], "percent": 100 * totals["covered_lines"] / totals["num_statements"]},
        "branch": {"covered": totals["covered_branches"], "total": totals["num_branches"], "percent": 100 * totals["covered_branches"] / totals["num_branches"]},
        "partial_branches": totals["num_partial_branches"], "combined_percent": totals["percent_covered"],
        "threshold": None, "gate_policy": "Measurement required; no invented percentage threshold"}


def evaluation_result(path, process_code):
    data = json.loads(path.read_text())
    if data.get("status") in {"passed", "failed"}:
        if data.get("classification_size", 0) <= 0 or data.get("retrieval_size", 0) <= 0:
            raise ValueError("Evaluation sample counts missing")
        if len(data.get("classification", [])) != data["classification_size"] or len(data.get("retrieval", [])) != data["retrieval_size"]:
            raise ValueError("Evaluation rows incomplete")
    return {"status": data.get("status"), "exit_code": process_code, "gate": data.get("gate"),
        "classification_size": data.get("classification_size"), "retrieval_size": data.get("retrieval_size"),
        "intent_correct": data.get("intent_correct"), "priority_correct": data.get("priority_correct"),
        "hit_at_4": data.get("hit_at_4"), "mrr": data.get("mrr"), "vector_queries": data.get("vector_queries"),
        "dataset_sha256": data.get("dataset_sha256"), "profile": data.get("profile")}


def decide_gate(pytest, evaluation, coverage, blocking_defects=()):
    incomplete, failed = [], []
    if pytest.get("status") != "completed" or pytest.get("exit_code") not in (0, 1):
        incomplete.append("pytest_incomplete")
    else:
        counts = pytest["counts"]
        if counts["tests"] == 0:
            incomplete.append("no_tests")
        if pytest["exit_code"] or counts["failed"] or counts["errors"]:
            failed.append("pytest_failed")
        if counts["skipped"]:
            failed.append("unexpected_skips")
        if pytest["baseline"]["missing_or_duplicate"]:
            failed.append("baseline_cases_missing_or_duplicate")
    if evaluation.get("exit_code") not in (0, 1) or evaluation.get("status") not in ("passed", "failed"):
        incomplete.append("evaluation_incomplete")
    elif evaluation["exit_code"] != 0 or evaluation["status"] != "passed" or evaluation.get("gate", {}).get("passed") is not True:
        failed.append("evaluation_failed")
    if coverage.get("status") != "completed":
        incomplete.append("coverage_incomplete")
    if blocking_defects:
        failed.append("blocking_open_defects")
    code = 2 if incomplete else 1 if failed else 0
    return {"status": "incomplete" if code == 2 else "failed" if code else "passed", "exit_code": code,
        "reasons": incomplete + failed, "scope": "offline deterministic checks only; not a production release approval"}


def quality_markdown(result):
    counts = result["pytest"].get("counts", {})
    lines = ["# OpsDesk 离线质量报告", "", f"门禁：**{result['gate']['status']}**；退出码：{result['gate']['exit_code']}",
        f"Git：`{result['git']['head']}`；源码修改：{bool(result['git']['dirty_source'])}。实际版本以source_sha256为准。",
        f"Python：{result['environment']['python']}；profile：{result['profile']}。", "",
        f"Pytest：{counts.get('passed', 0)} passed / {counts.get('failed', 0)} failed / {counts.get('errors', 0)} errors / {counts.get('skipped', 0)} skipped；合计{counts.get('tests', 0)}。",
        f"原109项：{result['pytest'].get('baseline', {}).get('passed', 0)}通过；缺失/重复名单见JSON。",
        f"规则/BM25评估：{result['evaluation'].get('status', 'error')}；退出码{result['evaluation'].get('exit_code')}。", ""]
    cov = result["coverage"]
    if cov.get("status") == "completed":
        lines += [f"行覆盖：{cov['line']['covered']}/{cov['line']['total']} = {cov['line']['percent']:.2f}%；分支覆盖：{cov['branch']['covered']}/{cov['branch']['total']} = {cov['branch']['percent']:.2f}%。",
                  "覆盖率只测Pytest中的业务模块；包括Mock路径，不代表真实基础设施验收。当前没有百分比门槛。", ""]
    else:
        lines += ["覆盖率：无法完成，门禁不能通过。", ""]
    lines += ["## 门禁理由", ""] + ["- " + reason for reason in (result["gate"]["reasons"] or ["全部离线必需检查完成并通过"])]
    lines += ["", "## 未关闭缺陷与残余风险", ""]
    lines += [f"- {d['id']}：{d['status']}；{d['summary']}" for d in result["quality_status"]["defects"] if d["status"] != "closed_offline"] or ["- 原审计登记缺陷在声明的离线范围内已关闭；不代表没有其他缺陷。"]
    lines += ["- " + risk for risk in result["quality_status"]["residual_risks"]]
    lines += ["", "## not_run / 真实环境受阻", ""]
    lines += [f"- {item['id']}：{item['status']}；{item['reason']}" for item in result["not_run"]]
    lines += ["", "远程CI未由本地报告证明；不得将not_run计入passed。",
        "报告：junit.xml、summary.json、coverage.json/xml/txt、evaluation.json、pytest-output.txt。", ""]
    return "\n".join(lines)


def run_process(command, cwd, env, timeout):
    try:
        process = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, timeout=timeout)
        return process.returncode, process.stdout + process.stderr
    except subprocess.TimeoutExpired:
        return None, "Execution timed out; incomplete result\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    started = datetime.now(timezone.utc)
    out = (args.output or REPO / "artifacts/qa" / started.strftime("%Y%m%dT%H%M%S%fZ")).resolve()
    if out.exists():
        parser.error("Output directory must be new; historical evidence must not be overwritten")
    out.mkdir(parents=True)
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain", "--", "opsdesk", "tests", "scripts", "evaluation", "knowledge", "skills", "requirements-dev.txt", "pyproject.toml", ".github/workflows/qa.yml", "docs/qa/quality-status.json"], cwd=REPO, text=True).splitlines()
    except subprocess.CalledProcessError:
        head, dirty = "unavailable", ["Git metadata unavailable"]
    result = {"schema_version": 1, "started_at": started.isoformat(), "git": {"head": head, "dirty_source": dirty},
        "profile": "offline / temporary SQLite / model-vector stubs / network connections blocked",
        "environment": {"python": platform.python_version(), "system": platform.system(), "dependencies": {}},
        "source_sha256": source_hashes(REPO), "pytest": {"status": "error", "exit_code": None},
        "evaluation": {"status": "error", "exit_code": None}, "coverage": {"status": "error"},
        "quality_status": {"defects": [], "residual_risks": []}, "not_run": []}
    for name in DEPENDENCIES:
        try: result["environment"]["dependencies"][name] = version(name)
        except PackageNotFoundError: result["environment"]["dependencies"][name] = None
    try:
        required = json.loads((REPO / "scripts/qa/baseline_cases.json").read_text())["cases"]
        if len(required) != 109 or len(set(required)) != 109:
            raise ValueError("Original baseline case manifest is invalid")
        registry = json.loads((REPO / "docs/qa/quality-status.json").read_text())
        result["quality_status"] = {"defects": registry["defects"], "residual_risks": registry["residual_risks"]}
        result["not_run"] = registry["not_run"]
        with tempfile.TemporaryDirectory(prefix="opsdesk-quality-") as temporary:
            root = Path(temporary)
            env = isolated_environment(REPO, root)
            pytest_code, log = run_process([sys.executable, "-m", "coverage", "run", "--rcfile=" + str(REPO / "pyproject.toml"),
                "-m", "pytest", str(REPO / "tests"), "-c", str(REPO / "pyproject.toml"), "-p", "no:cacheprovider",
                "-p", "scripts.qa.offline_guard", "--basetemp=" + str(root / "pytest"), "--junitxml=" + str(root / "junit.xml"), "-q"], root, env, 180)
            (out / "pytest-output.txt").write_text(safe_text(log, (REPO, root)), encoding="utf-8")
            if (root / "junit.xml").exists():
                result["pytest"] = junit_result(root / "junit.xml", pytest_code, required)
                tree = ET.parse(root / "junit.xml")
                for node in tree.iter():
                    node.attrib.pop("hostname", None)
                    for key, value in list(node.attrib.items()): node.set(key, safe_text(value, (REPO, root)))
                    if node.text: node.text = safe_text(node.text, (REPO, root))
                tree.write(out / "junit.xml", encoding="utf-8", xml_declaration=True)
            for kind in ("json", "xml", "report"):
                destination = out / ("coverage.txt" if kind == "report" else "coverage." + kind)
                command = [sys.executable, "-m", "coverage", kind, "--rcfile=" + str(REPO / "pyproject.toml")]
                if kind != "report": command += ["-o", str(destination)]
                code, output = run_process(command, REPO, env, 30)
                if code != 0: raise ValueError("Coverage report generation failed")
                if kind == "report": destination.write_text(safe_text(output, (REPO, root)))
                elif kind == "json": destination.write_text(json.dumps(safe_value(json.loads(destination.read_text()), (REPO, root)), ensure_ascii=False, indent=2) + "\n")
                else: destination.write_text(safe_text(destination.read_text(), (REPO, root)))
            result["coverage"] = coverage_result(out / "coverage.json")
            evaluation_code, evaluation_log = run_process([sys.executable, str(REPO / "scripts/qa/offline_guard.py"),
                str(REPO / "scripts/evaluate.py"), "--cases", str(REPO / "evaluation/cases.json"), "--output", str(root / "evaluation.json")], root, env, 60)
            (out / "evaluation-output.txt").write_text(safe_text(evaluation_log, (REPO, root)))
            if (root / "evaluation.json").exists():
                data = json.loads((root / "evaluation.json").read_text())
                result["evaluation"] = evaluation_result(root / "evaluation.json", evaluation_code)
                (out / "evaluation.json").write_text(json.dumps(safe_value(data, (REPO, root)), ensure_ascii=False, indent=2) + "\n")
    except Exception as exc:
        # Never log DSNs or exception bodies; an incomplete stage cannot pass.
        result["runner_error"] = type(exc).__name__
    blocking = [d["id"] for d in result["quality_status"]["defects"] if d.get("blocking") and d["status"] != "closed_offline"]
    result["gate"] = decide_gate(result["pytest"], result["evaluation"], result["coverage"], blocking)
    if "runner_error" in result or source_hashes(REPO) != result["source_sha256"] or head == "unavailable":
        result["gate"].update(status="incomplete", exit_code=2)
        result["gate"]["reasons"].append("runner_error_or_source_changed_or_git_unavailable")
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    result["artifacts"] = sorted(p.name for p in out.iterdir() if p.is_file()) + ["summary.json", "quality-report.md"]
    (out / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "quality-report.md").write_text(quality_markdown(result), encoding="utf-8")
    print(json.dumps({"gate": result["gate"], "pytest": result["pytest"].get("counts"), "coverage": result["coverage"]}, ensure_ascii=False, indent=2))
    print("Reports:", out)
    return result["gate"]["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
