import asyncio
from collections import Counter
from hashlib import sha256
from io import BytesIO
import math
from pathlib import Path
import re
import unicodedata

from sqlalchemy import delete, select

from opsdesk.contracts import Evidence
from opsdesk.inference import embed, embedding_identity
from opsdesk.storage import DocumentSegment


def terms(value):
    normalized = unicodedata.normalize("NFKC", value).lower()
    pieces = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", normalized)
    output = []
    for piece in pieces:
        if re.fullmatch(r"[\u4e00-\u9fff]+", piece):
            output.extend(piece[i:i+2] for i in range(max(1, len(piece)-1)))
        else:
            output.append(piece)
    return output


class KnowledgeIndex:
    def __init__(self, database, config):
        self.database, self.config = database, config
        self.vector_state = {"enabled": config.vector_search, "ready": False, "count": 0}
        self.collection = None
        self.rebuild_lock = asyncio.Lock()

    def ingest(self, source, text):
        title = next((line.lstrip("# ") for line in text.splitlines() if line.startswith("#")), source)
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        segments, current = [], ""
        for paragraph in paragraphs:
            for start in range(0, len(paragraph), 779):
                piece = paragraph[start:start + 779]
                if current and len(current) + len(piece) + 1 > 900:
                    segments.append(current); current = current[-120:]
                current += "\n" + piece
        if current.strip(): segments.append(current.strip())
        with self.database.session.begin() as db:
            db.execute(delete(DocumentSegment).where(DocumentSegment.source == source))
            for position, segment in enumerate(segments):
                key = sha256(f"{source}:{position}:{segment}".encode()).hexdigest()
                db.add(DocumentSegment(id=key, source=source, title=title[:160], text=segment))
        self.vector_state["ready"] = False
        return len(segments)

    def seed(self):
        with self.database.session() as db:
            existing = set(db.scalars(select(DocumentSegment.source)))
        for path in sorted(Path(self.config.knowledge_directory).glob("*.md")):
            if path.name not in existing:
                self.ingest(path.name, path.read_text(encoding="utf-8"))

    def import_bytes(self, filename, content):
        suffix = Path(filename).suffix.lower()
        if suffix == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(content))
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        elif suffix in {".md", ".txt"}:
            text = content.decode("utf-8")
        else:
            raise ValueError("Supported knowledge formats: Markdown, text, PDF")
        if not text.strip(): raise ValueError("Document has no extractable text")
        from opsdesk.redaction import clean_text
        return self.ingest(Path(filename).name[:160], clean_text(text))

    def rows(self):
        with self.database.session() as db:
            return list(db.scalars(select(DocumentSegment).order_by(DocumentSegment.id)))

    async def rebuild_vectors(self):
        if not self.config.vector_search:
            raise ValueError("Vector search is disabled; enable OPSDESK_VECTOR_SEARCH")
        async with self.rebuild_lock:
            self.vector_state["ready"] = False
            import chromadb
            from chromadb.config import Settings
            rows = self.rows()
            identity = await embedding_identity(self.config)
            self.client = chromadb.PersistentClient(path=self.config.vector_directory, settings=Settings(anonymized_telemetry=False))
            existing = [c.name if hasattr(c, "name") else str(c) for c in self.client.list_collections()]
            if "it_evidence" in existing: self.client.delete_collection("it_evidence")
            self.collection = self.client.create_collection("it_evidence", embedding_function=None, metadata={"embedding_identity": identity, "hnsw:space": "cosine"})
            for start in range(0, len(rows), 16):
                batch = rows[start:start+16]
                vectors = await embed(self.config, ["search_document: " + r.text for r in batch])
                self.collection.add(ids=[r.id for r in batch], embeddings=vectors, documents=[r.text for r in batch], metadatas=[{"source": r.source} for r in batch])
            self.vector_state = {"enabled": True, "ready": True, "count": len(rows), "embedding_identity": identity}
            return self.vector_state

    async def restore_vectors(self):
        if not self.config.vector_search: return
        try:
            import chromadb
            from chromadb.config import Settings
            self.client = chromadb.PersistentClient(path=self.config.vector_directory, settings=Settings(anonymized_telemetry=False))
            self.collection = self.client.get_collection("it_evidence", embedding_function=None)
            identity = await embedding_identity(self.config)
            if self.collection.metadata.get("embedding_identity") != identity:
                raise ValueError("Embedding identity changed; rebuild required")
            row_ids = {r.id for r in self.rows()}
            indexed = set(self.collection.get(include=[])['ids'])
            if indexed != row_ids: raise ValueError("Knowledge content changed; rebuild required")
            self.vector_state.update(ready=True, count=self.collection.count(), embedding_identity=identity)
        except Exception as exc:
            self.vector_state.update(ready=False, error=str(exc)[:180])

    def lexical(self, query, rows):
        frequencies = [Counter(terms(r.title + " " + r.text)) for r in rows]
        lengths = [sum(counts.values()) for counts in frequencies]
        average = sum(lengths) / max(1, len(lengths))
        query_terms = set(terms(query))
        ranked = []
        for index, row in enumerate(rows):
            score = 0
            for term in query_terms:
                tf = frequencies[index][term]
                if not tf: continue
                containing = sum(term in counts for counts in frequencies)
                rarity = math.log1p((len(rows) - containing + .5) / (containing + .5))
                normalization = tf + 1.4 * (.25 + .75 * lengths[index] / max(average, 1))
                score += rarity * (tf * 2.4) / normalization
            if score > 0: ranked.append((row.id, score))
        return sorted(ranked, key=lambda pair: (-pair[1], pair[0]))

    async def search(self, query, limit=4):
        rows = self.rows()
        if not rows: return []
        channels = {"bm25": self.lexical(query, rows)}
        if self.config.vector_search and self.vector_state.get("ready"):
            try:
                identity = await embedding_identity(self.config)
                if identity != self.vector_state["embedding_identity"]:
                    self.vector_state.update(ready=False, error="Embedding identity changed; rebuild required")
                    raise ValueError("Vector model changed")
                vector = (await embed(self.config, ["search_query: " + query]))[0]
                result = self.collection.query(query_embeddings=[vector], n_results=min(8, len(rows)))
                channels["vector"] = list(zip(result["ids"][0], result["distances"][0]))
            except Exception as exc:
                self.vector_state["last_query_error"] = type(exc).__name__
        scores, origins = Counter(), {}
        for channel, ranking in channels.items():
            for rank, (key, _) in enumerate(ranking[:12], 1):
                scores[key] += 1 / (40 + rank)
                origins.setdefault(key, []).append(channel)
        lookup = {row.id: row for row in rows}
        requested = set(terms(query))
        for key in scores:
            affinity = len(requested & set(terms(lookup[key].title))) / max(1, len(requested))
            scores[key] *= 1 + .2 * affinity
        winners = sorted(scores, key=lambda key: (-scores[key], key))[:limit]
        return [Evidence(segment_id=key, source=lookup[key].source, title=lookup[key].title, excerpt=lookup[key].text[:1200], score=round(scores[key], 6), channels=origins[key]) for key in winners]
