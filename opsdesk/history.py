import json

from sqlalchemy import select

from opsdesk.storage import Entry


class ConversationMemory:
    def __init__(self, database, config):
        self.database = database
        self.cache = None
        self.observations = {"hits": 0, "sql_reads": 0, "cache_errors": 0}
        if config.redis_url:
            import redis
            self.cache = redis.Redis.from_url(config.redis_url, socket_timeout=.5, socket_connect_timeout=.5, decode_responses=True)

    def cache_key(self, owner, thread):
        return f"opsdesk:v1:history:{owner}:{thread}"

    def recall(self, owner, thread):
        if self.cache is not None:
            try:
                cached = self.cache.get(self.cache_key(owner, thread))
                if cached:
                    self.observations["hits"] += 1
                    return self.compact(json.loads(cached), "redis")
            except Exception:
                self.observations["cache_errors"] += 1
        with self.database.session() as db:
            rows = list(db.scalars(select(Entry).where(Entry.thread_id == thread).order_by(Entry.id.desc()).limit(40)))[::-1]
            messages = [{"role": row.speaker, "content": row.text} for row in rows]
        self.observations["sql_reads"] += 1
        self.refresh(owner, thread, messages)
        return self.compact(messages, "sql")

    def refresh(self, owner, thread, messages=None):
        if self.cache is None: return
        try:
            if messages is None:
                with self.database.session() as db:
                    rows = list(db.scalars(select(Entry).where(Entry.thread_id == thread).order_by(Entry.id.desc()).limit(40)))[::-1]
                    messages = [{"role": r.speaker, "content": r.text} for r in rows]
            self.cache.setex(self.cache_key(owner, thread), 1800, json.dumps(messages, ensure_ascii=False))
        except Exception:
            self.observations["cache_errors"] += 1

    @staticmethod
    def compact(messages, source):
        recent, previous = messages[-6:], messages[:-6]
        brief = "Earlier employee issues: " + " | ".join(m["content"][:90] for m in previous if m["role"] == "user") if previous else ""
        return {"recent": [{"role": m["role"], "content": m["content"][:600]} for m in recent], "summary": brief[:700], "source": source, "compacted": bool(previous)}
