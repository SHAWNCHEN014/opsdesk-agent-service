"""Retain actual evaluator process outputs with temporary SQLite and samples.

Usage: <venv Python> <this file> --output <new directory> [--baseline]
Baseline redirects only PROJECT at runtime; repaired code uses the real CLI.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[4]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "summary.json").exists():
        parser.error("Choose a new directory to preserve prior results")
    source = Path(__file__).parent / "before-source/scripts/evaluate.py" if args.baseline else repo / "scripts/evaluate.py"
    results = []
    baseline = (repo / "evaluation/cases.json").read_bytes()
    for name, expected_code in (("baseline", 0), ("priority-mismatch", 1), ("retrieval-miss", 1), ("mrr-threshold", 1), ("missing-data", 2), ("empty-data", 2)):
        with tempfile.TemporaryDirectory(prefix="opsdesk-gate-") as directory:
            root = Path(directory)
            cases = json.loads(baseline)
            if name == "priority-mismatch":
                cases["classification"][0][2] = "P1"
            if name == "retrieval-miss":
                cases["retrieval"][0][0] = "zzzznevermatchingterm"
            if name == "empty-data":
                cases = {"classification": [], "retrieval": []}
            case_file = root / "evaluation/cases.json"
            case_file.parent.mkdir()
            if name != "missing-data":
                case_file.write_bytes(baseline if name == "baseline" else json.dumps(cases, ensure_ascii=False).encode())
            report_file = root / "artifacts/evaluation.json"
            cli = ["--cases", str(case_file), "--output", str(report_file)]
            if name == "mrr-threshold":
                cli += ["--min-mrr", "1"]
            env = {key: value for key, value in os.environ.items() if not key.startswith("OPSDESK_")}
            env.update(PYTHONPATH=str(repo), PYTHONDONTWRITEBYTECODE="1", OPSDESK_DATABASE_URL="sqlite:///" + str(root / "eval.db"),
                OPSDESK_MODEL_MODE="demo", OPSDESK_VECTOR_SEARCH="false", OPSDESK_REDIS_URL="", OPSDESK_WORKER_ENABLED="false",
                OPSDESK_LEDGER_FILE=str(root / "ledger.xlsx"), OPSDESK_VECTOR_DIRECTORY=str(root / "vectors"))
            if args.baseline:
                wrapper = "import asyncio,runpy,sys; from pathlib import Path; source,root=sys.argv[1:3]; sys.argv=[source]+sys.argv[3:]; ns=runpy.run_path(source,run_name='baseline'); ns['main'].__globals__['PROJECT']=Path(root); raise SystemExit(asyncio.run(ns['main']()))"
                command = [sys.executable, "-c", wrapper, str(source), str(root), *cli]
            else:
                command = [sys.executable, str(source), *cli]
            process = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=30)
            log = (process.stdout + process.stderr).replace(str(repo), "<REPO>").replace(str(root), "<TEMP>")
            (output / (name + ".txt")).write_text(log, encoding="utf-8")
            report = json.loads(report_file.read_text()) if report_file.exists() else None
            if report is not None:
                (output / (name + ".json")).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            results.append({"case": name, "expected_exit_code": expected_code, "actual_exit_code": process.returncode,
                "status": report.get("status") if report else None, "expectation_met": process.returncode == expected_code})
    summary = {"at": datetime.now(timezone.utc).isoformat(), "source_sha256": sha256(source.read_bytes()).hexdigest(),
        "baseline_dataset_sha256": sha256(baseline).hexdigest(), "source": "original" if args.baseline else "repaired",
        "invocation": "runpy PROJECT redirection" if args.baseline else "actual __main__ CLI",
        "profile": "temporary SQLite / BM25 / deterministic rules / no .env or network", "cases": results}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if all(case["expectation_met"] for case in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
