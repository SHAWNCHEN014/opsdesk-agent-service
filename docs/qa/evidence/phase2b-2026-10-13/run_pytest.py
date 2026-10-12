"""Repeat offline Pytest without .env, existing var files or optional plugins.

Usage: <repo>/.venv/bin/python <this file> --output <new evidence directory>
The process exit code is the actual Pytest exit code (including a red run).
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", action="store_true", help="Run final tests against the two saved Phase 2A source files in a disposable replica")
    parser.add_argument("--suite", choices=("full", "reliability"), default="full")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "pytest.xml").exists():
        parser.error("Choose a new output directory to preserve previous evidence")
    repo = Path(__file__).resolve().parents[4]
    started = datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix="opsdesk-phase2b-") as temporary:
        root = Path(temporary)
        execution_repo = repo
        if args.baseline:
            execution_repo = root / "baseline-replica"
            execution_repo.mkdir()
            for directory in ("opsdesk", "tests", "web", "knowledge", "skills"):
                shutil.copytree(repo / directory, execution_repo / directory, ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copyfile(repo / "pyproject.toml", execution_repo / "pyproject.toml")
            (execution_repo / "scripts").mkdir()
            shutil.copyfile(repo / "scripts/evaluate.py", execution_repo / "scripts/evaluate.py")
            for source in ("opsdesk/queueing.py", "opsdesk/main.py"):
                destination = execution_repo / source
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(Path(__file__).parent / "before-source" / source, destination)
        paths = sorted([*execution_repo.glob("opsdesk/*.py"), execution_repo / "scripts/evaluate.py", *execution_repo.glob("tests/**/*.py"), execution_repo / "evaluation/cases.json"])
        if args.baseline:
            (execution_repo / "evaluation").mkdir()
            shutil.copyfile(repo / "evaluation/cases.json", execution_repo / "evaluation/cases.json")
        source_sha256 = {str(path.relative_to(execution_repo)): sha256(path.read_bytes()).hexdigest() for path in paths}
        env = {k: v for k, v in os.environ.items() if not k.startswith("OPSDESK_")}
        env.update(PYTHONPATH=str(execution_repo), PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
        target = execution_repo / "tests" if args.suite == "full" else execution_repo / "tests/reliability"
        command = [sys.executable, "-m", "pytest", str(target), "-c", str(execution_repo / "pyproject.toml"),
            "-p", "no:cacheprovider", "--basetemp", str(root / "pytest"), "--junitxml=" + str(root / "pytest.xml"), "-q"]
        process = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=180)
        log = (process.stdout + process.stderr).replace(str(execution_repo), "<REPO>").replace(str(repo), "<REPO>").replace(str(root), "<TEMP>")
        (output / "pytest-output.txt").write_text(log, encoding="utf-8")
        tree = ET.parse(root / "pytest.xml")
        counts = dict(tests=0, failures=0, errors=0, skipped=0, seconds=0.0)
        for suite in tree.findall("testsuite"):
            suite.attrib.pop("hostname", None)
            for key in ("tests", "failures", "errors", "skipped"):
                counts[key] += int(suite.get(key, "0"))
            counts["seconds"] += float(suite.get("time", "0"))
        for element in tree.iter():
            if element.text:
                element.text = element.text.replace(str(execution_repo), "<REPO>").replace(str(repo), "<REPO>").replace(str(root), "<TEMP>")
        tree.write(output / "pytest.xml", encoding="utf-8", xml_declaration=True)
    counts["passed"] = counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"]
    cases = tree.findall(".//testcase")
    original = [case for case in cases if case.get("classname") == "tests.test_service"]
    original_passed = sum(not any(case.find(tag) is not None for tag in ("failure", "error", "skipped")) for case in original)
    baseline_cases = [case for case in cases if not case.get("classname", "").startswith("tests.reliability.")]
    baseline_passed = sum(not any(case.find(tag) is not None for tag in ("failure", "error", "skipped")) for case in baseline_cases)
    observations = []
    for case in cases:
        for prop in case.findall("properties/property"):
            if prop.get("name") == "reliability_evidence":
                observations.append({"case": case.get("name"), "observed": json.loads(prop.get("value"))})
    (output / "scenario-observations.json").write_text(json.dumps(observations, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--", "opsdesk", "tests", "scripts/evaluate.py", "evaluation/cases.json"], cwd=repo, text=True).splitlines()
    result = {"started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "version_note": "Phase 2A baseline source replica; HEAD is the runner's current repository version." if args.baseline else "Working source is dirty; verify source_sha256." if dirty else "Source and tests match HEAD; evidence documents may be uncommitted.",
        "source_git_status": dirty,
        "dependencies": {name: version(name) for name in ("pytest", "SQLAlchemy", "FastAPI", "httpx", "openpyxl", "mcp", "anyio", "PyMySQL")},
        "python": platform.python_version(), "profile": "offline / temporary SQLite / model and vector stubs / no Redis",
        "suite": args.suite,
        "exit_code": process.returncode, "pytest": counts, "original_cases": len(original), "original_passed": original_passed, "phase2a_cases": len(baseline_cases), "phase2a_passed": baseline_passed,
        "source_sha256": source_sha256,
        "not_run": ["real Ollama/Chroma", "MySQL/Redis", "Docker", "load/soak", "coverage", "CI deployment"]}
    (output / "run-summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "source_sha256"}, ensure_ascii=False, indent=2))
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
