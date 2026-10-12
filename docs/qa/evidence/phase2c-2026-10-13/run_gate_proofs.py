"""Local CI-command failure proofs in disposable repository replicas.

No remote operations. Original test/gold/source files are never mutated.
The replica's Git HEAD is the real repository HEAD, with copied working files
identified as dirty by the unified runner's source hashes.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import yaml


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("failures", "baseline"), default="failures")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[4]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    workflow = yaml.load((repo / ".github/workflows/qa.yml").read_text(), Loader=yaml.BaseLoader)
    command = next(step["run"] for step in workflow["jobs"]["offline"]["steps"] if step.get("name") == "Run required quality gate")
    assert command == "python scripts/qa/run_checks.py --output artifacts/qa/ci"
    scenarios = ("pytest_failure", "evaluation_failure", "missing_dataset") if args.mode == "failures" else ("phase2b_business_baseline",)
    runs = []
    for scenario in scenarios:
        with tempfile.TemporaryDirectory(prefix="opsdesk-gate-proof-") as temporary:
            replica = Path(temporary) / "repo"
            subprocess.run(["git", "clone", "--shared", "--quiet", str(repo), str(replica)], check=True, capture_output=True)
            for directory in ("opsdesk", "tests", "scripts", "web", "knowledge", "skills", "evaluation", ".github"):
                shutil.copytree(repo / directory, replica / directory, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
            for path in ("pyproject.toml", "requirements-dev.txt", "requirements.txt", "docs/qa/quality-status.json"):
                destination = replica / path; destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(repo / path, destination)
            if scenario == "pytest_failure":
                (replica / "tests/quality/test_intentional_failure.py").write_text('def test_safe_gate_failure():\n    assert False, "Synthetic intentional quality gate failure"\n')
            elif scenario == "evaluation_failure":
                path = replica / "evaluation/cases.json"
                data = json.loads(path.read_text())
                data["classification"][0][2] = "P2" if data["classification"][0][2] != "P2" else "P3"
                path.write_text(json.dumps(data, ensure_ascii=False))
            elif scenario == "missing_dataset":
                (replica / "evaluation/cases.json").unlink()
            else:
                for path in ("opsdesk/queueing.py", "opsdesk/main.py", "opsdesk/contracts.py"):
                    shutil.copyfile(Path(__file__).parent / "before-source" / path, replica / path)
            destination = output / scenario
            # Execute the workflow's exact Python CLI using this tested interpreter.
            process = subprocess.run([sys.executable, "scripts/qa/run_checks.py", "--output", "artifacts/qa/ci"], cwd=replica, capture_output=True, text=True, timeout=240)
            shutil.copytree(replica / "artifacts/qa/ci", destination)
            (destination / "cli-output.txt").write_text((process.stdout + process.stderr).replace(str(replica), "<REPLICA>"))
            result = json.loads((destination / "summary.json").read_text())
            expected = 2 if scenario == "missing_dataset" else 1
            assert process.returncode == result["gate"]["exit_code"] == expected, result["gate"]
            if scenario == "pytest_failure": assert "pytest_failed" in result["gate"]["reasons"]
            if scenario == "evaluation_failure": assert "evaluation_failed" in result["gate"]["reasons"]
            if scenario == "missing_dataset": assert "evaluation_incomplete" in result["gate"]["reasons"]
            runs.append({"scenario": scenario, "command": command, "process_exit_code": process.returncode,
                "gate": result["gate"], "pytest": result["pytest"].get("counts"), "baseline109": result["pytest"].get("baseline"),
                "evaluation": result["evaluation"], "source_sha256": result["source_sha256"], "replica_head": result["git"]["head"]})
            print(scenario, process.returncode, result["gate"]["reasons"], flush=True)
    (output / "proof-summary.json").write_text(json.dumps({"status": "expected_failures_observed", "remote_ci": "not_run", "scenarios": runs}, ensure_ascii=False, indent=2) + "\n")
    return 0  # Expected negative outcomes verified, not candidate versions passing.


if __name__ == "__main__":
    raise SystemExit(main())
