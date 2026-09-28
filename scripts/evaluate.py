import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from opsdesk.configuration import PROJECT, Configuration
from opsdesk.orchestration import heuristic_intake, impact_priority
from opsdesk.retrieval import KnowledgeIndex
from opsdesk.storage import Database


async def main():
    cases = json.loads((PROJECT / "evaluation/cases.json").read_text(encoding="utf-8"))
    classification = []
    for text, intent, priority in cases["classification"]:
        actual = heuristic_intake(text)
        level = impact_priority(actual).level
        classification.append({"text": text, "expected_intent": intent, "actual_intent": actual.intent, "expected_priority": priority, "actual_priority": level})
    config = Configuration()
    db = Database(config)
    db.initialize()
    knowledge = KnowledgeIndex(db, config)
    knowledge.seed()
    await knowledge.restore_vectors()
    retrieval = []
    for query, expected in cases["retrieval"]:
        results = await knowledge.search(query)
        ranking = [item.source for item in results]
        rank = next((index + 1 for index, source in enumerate(ranking) if source == expected), None)
        retrieval.append({"query": query, "expected": expected, "ranking": ranking, "rank": rank, "vector_used": any("vector" in item.channels for item in results)})
    report = {"at": datetime.now(timezone.utc).isoformat(), "scope": "Small self-authored synthetic regression set. Classification tests the deterministic fallback only, not model accuracy. Retrieval reflects the explicitly recorded runtime channels. No held-out or production claim.", "classification_size": len(classification), "intent_correct": sum(item["expected_intent"] == item["actual_intent"] for item in classification), "priority_correct": sum(item["expected_priority"] == item["actual_priority"] for item in classification), "retrieval_size": len(retrieval), "hit_at_4": sum(item["rank"] is not None for item in retrieval) / len(retrieval), "mrr": sum(1 / item["rank"] if item["rank"] else 0 for item in retrieval) / len(retrieval), "vector_queries": sum(item["vector_used"] for item in retrieval), "classification": classification, "retrieval": retrieval}
    output = PROJECT / "artifacts/evaluation.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in {"classification", "retrieval"}}, ensure_ascii=False))
    db.engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
