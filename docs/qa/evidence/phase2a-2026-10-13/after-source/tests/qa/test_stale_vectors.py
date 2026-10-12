"""QA-RAG-01: real fusion with controlled embedding/vector adapters."""
import asyncio

import pytest
from sqlalchemy import delete

from opsdesk import retrieval
from opsdesk.storage import DocumentSegment


def attach_vectors(monkeypatch, knowledge, ids, failure=None):
    async def identity(_):
        return "synthetic-embedding-v1"

    async def embed(_, texts):
        return [[1.0, 0.0] for _ in texts]

    class Collection:
        calls = 0

        def query(self, **kwargs):
            self.calls += 1
            if failure:
                raise failure
            return {"ids": [ids], "distances": [[.01 * i for i in range(len(ids))]]}

    monkeypatch.setattr(retrieval, "embedding_identity", identity)
    monkeypatch.setattr(retrieval, "embed", embed)
    knowledge.config.vector_search = True
    knowledge.vector_state.update(enabled=True, ready=True, embedding_identity="synthetic-embedding-v1")
    knowledge.collection = Collection()
    return knowledge.collection


@pytest.mark.parametrize("kind", ["missing", "mixed", "deleted"], ids=["unknown-id", "mixed-valid-stale", "deleted-id"])
def test_stale_ids_fall_back_to_exact_bm25_and_disable_index(runtime, monkeypatch, kind):
    _, db, knowledge, _, _, _ = runtime
    rows = knowledge.rows()
    stale = "no-longer-in-sql"
    if kind == "deleted":
        stale = rows[0].id
        with db.session.begin() as session:
            session.execute(delete(DocumentSegment).where(DocumentSegment.id == stale))
    baseline = asyncio.run(knowledge.search("VPN"))
    ids = [stale] if kind != "mixed" else [knowledge.rows()[0].id, stale]
    collection = attach_vectors(monkeypatch, knowledge, ids)
    actual = asyncio.run(knowledge.search("VPN"))
    assert [item.model_dump() for item in actual] == [item.model_dump() for item in baseline]
    assert actual and all(item.channels == ["bm25"] for item in actual)
    assert knowledge.vector_state["ready"] is False
    assert knowledge.vector_state["last_query_error"] == "StaleVectorIndexError"
    assert "rebuild" in knowledge.vector_state["error"].lower()
    assert asyncio.run(knowledge.search("VPN")) == actual
    assert collection.calls == 1  # Broken index isn't queried repeatedly.


def test_valid_hybrid_preserves_rrf_and_title_reranking(runtime, monkeypatch):
    _, _, knowledge, _, _, _ = runtime
    rows = knowledge.rows()
    query = "VPN"
    lexical = knowledge.lexical(query, rows)
    ids = [key for key, _ in reversed(lexical)]
    attach_vectors(monkeypatch, knowledge, ids)
    expected_scores, origins = {}, {}
    for channel, ranked_ids in (("bm25", [key for key, _ in lexical]), ("vector", ids)):
        for rank, key in enumerate(ranked_ids[:12], 1):
            expected_scores[key] = expected_scores.get(key, 0) + 1 / (40 + rank)
            origins.setdefault(key, []).append(channel)
    lookup = {row.id: row for row in rows}
    query_terms = set(retrieval.terms(query))
    for key in expected_scores:
        affinity = len(query_terms & set(retrieval.terms(lookup[key].title))) / max(1, len(query_terms))
        expected_scores[key] *= 1 + .2 * affinity
    expected_ids = sorted(expected_scores, key=lambda key: (-expected_scores[key], key))[:4]
    results = asyncio.run(knowledge.search(query))
    assert [item.segment_id for item in results] == expected_ids
    assert [item.score for item in results] == [round(expected_scores[key], 6) for key in expected_ids]
    assert [item.channels for item in results] == [origins[key] for key in expected_ids]
    assert knowledge.vector_state["ready"] is True


def test_vector_timeout_preserves_bm25_and_records_error(runtime, monkeypatch):
    _, _, knowledge, _, _, _ = runtime
    baseline = asyncio.run(knowledge.search("VPN"))
    attach_vectors(monkeypatch, knowledge, [], TimeoutError("synthetic timeout"))
    assert asyncio.run(knowledge.search("VPN")) == baseline
    assert knowledge.vector_state["last_query_error"] == "TimeoutError"


def test_empty_sql_corpus_does_not_query_vectors(runtime, monkeypatch):
    _, db, knowledge, _, _, _ = runtime
    with db.session.begin() as session:
        session.execute(delete(DocumentSegment))
    collection = attach_vectors(monkeypatch, knowledge, ["stale"])
    assert asyncio.run(knowledge.search("VPN")) == []
    assert collection.calls == 0
