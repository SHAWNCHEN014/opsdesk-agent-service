import argparse
import asyncio
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from opsdesk.configuration import PROJECT, Configuration
from opsdesk.orchestration import heuristic_intake, impact_priority
from opsdesk.retrieval import KnowledgeIndex
from opsdesk.storage import Database


def probability(value):
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise argparse.ArgumentTypeError("Threshold must be finite and between 0 and 1")
    return number


def validate_cases(cases):
    if not isinstance(cases, dict):
        raise ValueError("Dataset must contain classification and retrieval lists")
    for name, width in (("classification", 3), ("retrieval", 2)):
        rows = cases.get(name)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"{name} must be a nonempty list")
        for row in rows:
            if not isinstance(row, list) or len(row) != width or not all(isinstance(v, str) and v.strip() for v in row):
                raise ValueError(f"Invalid {name} row")
            if name == "classification" and (row[1] not in {"FAQ", "REQUEST", "INCIDENT"} or row[2] not in {"P1", "P2", "P3"}):
                raise ValueError("Invalid classification label")


def write_report(output, report):
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(suffix=".json", dir=output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)


async def main(argv=None):
    parser = argparse.ArgumentParser(description="Rules and retrieval regression gate; exit 0=pass, 1=failed metrics, 2=incomplete/error.")
    parser.add_argument("--cases", type=Path, default=PROJECT / "evaluation/cases.json")
    parser.add_argument("--output", type=Path, default=PROJECT / "artifacts/evaluation.json")
    parser.add_argument("--min-hit-at-4", type=probability, default=1.0)
    parser.add_argument("--min-mrr", type=probability, default=.9)
    args = parser.parse_args(argv)
    criteria = {"intent_accuracy": 1.0, "priority_accuracy": 1.0,
                "min_hit_at_4": args.min_hit_at_4, "min_mrr": args.min_mrr}
    report = {"at": datetime.now(timezone.utc).isoformat(),
        "scope": "Small self-authored synthetic regression set. Classification tests deterministic rules, not model accuracy. Retrieval is measured at segment ranks up to 4, matching expected source. No held-out or production claim.",
        "status": "error", "gate": {"passed": False, "criteria": criteria, "failures": []}}
    db, stage = None, "dataset"
    exit_code = 2
    try:
        data = args.cases.read_bytes()
        report["dataset_sha256"] = sha256(data).hexdigest()
        cases = json.loads(data)
        validate_cases(cases)
        classification = []
        for text, intent, priority in cases["classification"]:
            actual = heuristic_intake(text)
            level = impact_priority(actual).level
            classification.append({"text": text, "expected_intent": intent, "actual_intent": actual.intent, "expected_priority": priority, "actual_priority": level})
        stage = "configuration"
        config = Configuration()
        report["profile"] = "hybrid" if config.vector_search else "bm25"
        stage = "knowledge"
        db = Database(config)
        db.initialize()
        knowledge = KnowledgeIndex(db, config)
        knowledge.seed()
        rows = knowledge.rows()
        if not rows or not {expected for _, expected in cases["retrieval"]} <= {row.source for row in rows}:
            raise ValueError("Required reference documents are missing")
        report["knowledge_sha256"] = sha256(json.dumps([(row.id, row.source, row.title, row.text) for row in rows], ensure_ascii=False).encode()).hexdigest()
        await knowledge.restore_vectors()
        if config.vector_search and not knowledge.vector_state.get("ready"):
            raise ValueError("Required vector index is unavailable")
        stage = "retrieval"
        retrieval = []
        for query, expected in cases["retrieval"]:
            results = await knowledge.search(query, limit=4)
            ranking = [item.source for item in results]
            rank = next((index + 1 for index, source in enumerate(ranking) if source == expected), None)
            retrieval.append({"query": query, "expected": expected, "ranking": ranking, "rank": rank, "vector_used": any("vector" in item.channels for item in results)})
        report.update(classification_size=len(classification),
            intent_correct=sum(item["expected_intent"] == item["actual_intent"] for item in classification),
            priority_correct=sum(item["expected_priority"] == item["actual_priority"] for item in classification),
            retrieval_size=len(retrieval), hit_at_4=sum(item["rank"] is not None for item in retrieval) / len(retrieval),
            mrr=sum(1 / item["rank"] if item["rank"] else 0 for item in retrieval) / len(retrieval),
            vector_queries=sum(item["vector_used"] for item in retrieval), classification=classification, retrieval=retrieval)
        if config.vector_search and report["vector_queries"] != len(retrieval):
            raise ValueError("Required hybrid evaluation degraded; not every query used vectors")
        failures = report["gate"]["failures"]
        for metric in ("intent_correct", "priority_correct"):
            if report[metric] != len(classification):
                failures.append(metric)
        if report["hit_at_4"] < args.min_hit_at_4:
            failures.append("hit_at_4")
        if report["mrr"] < args.min_mrr:
            failures.append("mrr")
        report["gate"]["passed"] = not failures
        report["status"] = "failed" if failures else "passed"
        exit_code = 1 if failures else 0
    except Exception as exc:
        # Do not echo connection URLs, validation input values or private text.
        report["errors"] = [{"stage": stage, "type": type(exc).__name__}]
    finally:
        if db is not None:
            db.engine.dispose()
    try:
        write_report(args.output, report)
    except OSError as exc:
        report.update(status="error", errors=[{"stage": "report", "type": type(exc).__name__}])
        report["gate"]["passed"] = False
        exit_code = 2
    print(json.dumps({key: value for key, value in report.items() if key not in {"classification", "retrieval"}}, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
