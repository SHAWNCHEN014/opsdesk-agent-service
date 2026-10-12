import asyncio
import json
import os
import sys
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from sqlalchemy import select, update

from opsdesk.actions import ActionHandlers
from opsdesk.configuration import PROJECT
from opsdesk.storage import ActionHistory, QueuedAction, new_id, timestamp


def enqueue(db, request_id, priority):
    first = QueuedAction(id=new_id(), request_id=request_id, kind="create_work_order")
    db.add(first)
    db.flush()
    db.add(QueuedAction(request_id=request_id, kind="export_ledger", depends_on=first.id))
    if priority == "P1":
        db.add(QueuedAction(request_id=request_id, kind="notify_escalation", depends_on=first.id))


class ActionWorker:
    def __init__(self, database, config):
        self.database, self.config = database, config
        self.handlers = ActionHandlers(database, config)
        self.stopping = False

    def claim(self):
        now = timestamp()
        with self.database.session.begin() as db:
            # Expired leases become retryable, with an explicit recovery audit.
            for action in db.scalars(select(QueuedAction).where(QueuedAction.phase == "RUNNING", QueuedAction.lease_until < now)):
                changed = db.execute(update(QueuedAction).where(QueuedAction.id == action.id, QueuedAction.lease == action.lease, QueuedAction.phase == "RUNNING").values(phase="DEAD" if action.tries >= self.config.max_action_attempts else "READY", lease="", lease_until=None, due=now, last_error="Lease expired before completion"))
                if changed.rowcount:
                    db.add(ActionHistory(action_id=action.id, attempt=action.tries, result="LEASE_EXPIRED", transport=self.config.action_transport, detail={}))
            candidates = list(db.scalars(select(QueuedAction).where(QueuedAction.phase == "READY", QueuedAction.due <= now).order_by(QueuedAction.due).limit(30)))
            for action in candidates:
                parent = db.get(QueuedAction, action.depends_on) if action.depends_on else None
                if parent and parent.phase == "DEAD":
                    action.phase, action.last_error = "DEAD", "Dependency failed; retry parent first"
                    continue
                if parent and parent.phase != "DONE":
                    continue
                lease = new_id()
                changed = db.execute(update(QueuedAction).where(QueuedAction.id == action.id, QueuedAction.phase == "READY").values(phase="RUNNING", tries=QueuedAction.tries + 1, lease=lease, lease_until=now + timedelta(seconds=90)))
                if changed.rowcount:
                    return {"id": action.id, "request_id": action.request_id, "kind": action.kind, "lease": lease}
        return None

    async def invoke(self, action):
        if self.config.action_transport == "direct":
            return await asyncio.to_thread(self.handlers.dispatch, action["kind"], action["request_id"])
        if self.config.action_transport != "mcp":
            raise ValueError("Unsupported action transport")
        env = {**os.environ, **{"OPSDESK_" + key.upper(): str(value).lower() if isinstance(value, bool) else str(value) for key, value in self.config.model_dump().items()}}
        parameters = StdioServerParameters(command=sys.executable, args=["-m", "opsdesk.action_server"], cwd=PROJECT, env=env)
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                response = await session.call_tool(action["kind"], {"request_id": action["request_id"]})
                if response.isError:
                    raise ValueError("MCP action rejected: " + " ".join(part.text for part in response.content if part.type == "text")[:300])
                if response.structuredContent is not None:
                    return response.structuredContent
                return json.loads(next(part.text for part in response.content if part.type == "text"))

    def finish(self, action, result=None, error=None):
        with self.database.session.begin() as db:
            row = db.scalar(select(QueuedAction).where(QueuedAction.id == action["id"], QueuedAction.lease == action["lease"], QueuedAction.phase == "RUNNING").with_for_update())
            if row is None:
                return False
            row.lease, row.lease_until = "", None
            if error is None:
                row.phase, row.last_error = "DONE", ""
            else:
                row.phase = "DEAD" if row.tries >= self.config.max_action_attempts else "READY"
                row.due = timestamp() + timedelta(seconds=min(60, 2 ** row.tries))
                row.last_error = str(error)[:500]
            db.add(ActionHistory(action_id=row.id, attempt=row.tries, result="DONE" if error is None else "FAILED", transport=self.config.action_transport, detail=result if error is None else {"error": row.last_error}))
            return True

    async def step(self):
        action = self.claim()
        if not action:
            return False
        try:
            result = await asyncio.wait_for(self.invoke(action), timeout=60)
            self.finish(action, result=result)
        except Exception as exc:
            self.finish(action, error=exc)
        return True

    async def run(self):
        while not self.stopping:
            if not await self.step():
                await asyncio.sleep(0.4)

    def retry(self, action_id):
        with self.database.session.begin() as db:
            row = db.get(QueuedAction, action_id)
            if row is None or row.phase != "DEAD":
                raise ValueError("Only failed actions can be retried")
            if row.depends_on and db.get(QueuedAction, row.depends_on).phase != "DONE":
                raise ValueError("Retry and complete the dependency first")
            row.phase, row.tries, row.due, row.last_error = "READY", 0, timestamp(), ""
