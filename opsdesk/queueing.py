import asyncio
import json
import logging
import os
import sqlite3
import sys
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from sqlalchemy import or_, select, update
from sqlalchemy.exc import DBAPIError, TimeoutError as PoolTimeout
from sqlalchemy.orm import aliased

from opsdesk.actions import ActionHandlers
from opsdesk.configuration import PROJECT
from opsdesk.storage import ActionHistory, Identity, QueuedAction, new_id, timestamp


logger = logging.getLogger(__name__)
CLAIM_BATCH = 30


def retryable_database_error(error):
    """Retry known contention/connection failures, never guess from error text."""
    if isinstance(error, PoolTimeout):
        return True
    if not isinstance(error, DBAPIError):
        return False
    if error.connection_invalidated:
        return True
    original = error.orig
    if isinstance(original, sqlite3.Error):
        code = getattr(original, "sqlite_errorcode", None)
        return code is not None and (code & 0xFF) in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
    code = original.args[0] if original.args else None
    return code in {1040, 1205, 1213, 2002, 2003, 2006, 2013, 2055}


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
        self.observations = {"state": "stopped", "consecutive_errors": 0, "recoveries": 0, "last_error": None, "retry_delay": 0.0}

    def claim(self):
        now = timestamp()
        with self.database.session.begin() as db:
            # Expired leases become retryable, with an explicit recovery audit.
            for action in db.scalars(select(QueuedAction).where(QueuedAction.phase == "RUNNING", QueuedAction.lease_until < now).order_by(QueuedAction.lease_until, QueuedAction.id).limit(CLAIM_BATCH)):
                changed = db.execute(update(QueuedAction).where(QueuedAction.id == action.id, QueuedAction.lease == action.lease, QueuedAction.phase == "RUNNING").values(phase="DEAD" if action.tries >= self.config.max_action_attempts else "READY", lease="", lease_until=None, due=now, last_error="Lease expired before completion"))
                if changed.rowcount:
                    db.add(ActionHistory(action_id=action.id, attempt=action.tries, result="LEASE_EXPIRED", transport=self.config.action_transport, detail={}))
            exhausted = list(db.scalars(select(QueuedAction.id).where(QueuedAction.phase == "READY", QueuedAction.due <= now, QueuedAction.tries >= self.config.max_action_attempts).order_by(QueuedAction.due, QueuedAction.id).limit(CLAIM_BATCH)))
            if exhausted:
                db.execute(update(QueuedAction).where(QueuedAction.id.in_(exhausted), QueuedAction.phase == "READY").values(phase="DEAD", lease="", lease_until=None, last_error="Retry budget exhausted"))
            parent = aliased(QueuedAction)
            blocked = list(db.scalars(select(QueuedAction.id).join(parent, QueuedAction.depends_on == parent.id).where(QueuedAction.phase == "READY", QueuedAction.due <= now, parent.phase == "DEAD").order_by(QueuedAction.due, QueuedAction.id).limit(CLAIM_BATCH)))
            if blocked:
                db.execute(update(QueuedAction).where(QueuedAction.id.in_(blocked), QueuedAction.phase == "READY").values(phase="DEAD", lease="", lease_until=None, last_error="Dependency failed; retry parent first"))
            # Apply dependency eligibility before the bounded candidate window.
            # Cleanup windows cannot displace runnable work or consume retry budgets.
            candidates = list(db.scalars(select(QueuedAction).outerjoin(parent, QueuedAction.depends_on == parent.id).where(QueuedAction.phase == "READY", QueuedAction.due <= now, QueuedAction.tries < self.config.max_action_attempts, or_(QueuedAction.depends_on.is_(None), parent.phase == "DONE")).order_by(QueuedAction.due, QueuedAction.id).limit(CLAIM_BATCH)))
            for action in candidates:
                lease = new_id()
                changed = db.execute(update(QueuedAction).where(QueuedAction.id == action.id, QueuedAction.phase == "READY", QueuedAction.due <= now, QueuedAction.tries < self.config.max_action_attempts).values(phase="RUNNING", tries=QueuedAction.tries + 1, lease=lease, lease_until=now + timedelta(seconds=90)))
                if changed.rowcount:
                    return {"id": action.id, "request_id": action.request_id, "kind": action.kind, "lease": lease}
        return None

    async def invoke(self, action):
        if self.config.action_transport == "direct":
            call = asyncio.create_task(asyncio.to_thread(self.handlers.dispatch, action["kind"], action["request_id"]))
            try:
                return await asyncio.shield(call)
            except asyncio.CancelledError:
                # Threads cannot be killed safely. Keep ownership until dispatch
                # ends, before shutdown disposes the database or a restart begins.
                while not call.done():
                    try:
                        await asyncio.shield(call)
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        break
                if not call.cancelled() and call.exception() is not None:
                    logger.warning("Worker dispatch ended during cancellation: %s", type(call.exception()).__name__)
                raise
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
        except Exception as exc:
            self.finish(action, error=exc)
        else:
            # A failed completion write is a database fault, not a failed tool.
            # Preserve the lease and recover through normal expiry/idempotence.
            self.finish(action, result=result)
        return True

    async def _pause(self, delay):
        await asyncio.sleep(delay)

    async def run(self):
        if self.observations["state"] in {"running", "backoff"}:
            raise RuntimeError("Worker is already running")
        self.stopping = False
        self.observations.update(state="running", consecutive_errors=0, retry_delay=0.0)
        try:
            while not self.stopping:
                try:
                    worked = await self.step()
                except Exception as exc:
                    self.observations["last_error"] = type(exc).__name__
                    if not retryable_database_error(exc):
                        self.observations["state"] = "failed"
                        logger.error("Worker stopped; intervention required: %s", type(exc).__name__)
                        raise
                    errors = self.observations["consecutive_errors"] + 1
                    delay = min(30.0, 0.4 * 2 ** min(errors - 1, 7))
                    self.observations.update(state="backoff", consecutive_errors=errors, retry_delay=delay)
                    logger.warning("Worker database retry in %.1fs: %s", delay, type(exc).__name__)
                    await self._pause(delay)
                    continue
                if self.observations["consecutive_errors"]:
                    self.observations["recoveries"] += 1
                    logger.info("Worker database recovered")
                self.observations.update(state="running", consecutive_errors=0, retry_delay=0.0)
                if not worked:
                    await self._pause(0.4)
        finally:
            if self.observations["state"] != "failed":
                self.observations["state"] = "stopped"

    def retry(self, action_id, *, actor_id=None, reason="operator_reviewed"):
        failure = None
        with self.database.session.begin() as db:
            actor = db.get(Identity, actor_id) if actor_id is not None else None
            actor_detail = {"kind": "identity" if actor_id is not None else "system", "id": actor_id, "role": actor.role if actor else None}
            row = db.scalar(select(QueuedAction).where(QueuedAction.id == action_id).with_for_update())
            before = {"phase": row.phase, "tries": row.tries} if row else None
            parent = db.get(QueuedAction, row.depends_on) if row and row.depends_on else None
            if actor_id is not None and (actor is None or actor.role != "engineer"):
                outcome, failure = "forbidden", PermissionError("Engineer role required")
            elif reason not in {"issue_resolved", "dependency_restored", "operator_reviewed"}:
                outcome, failure = "invalid_reason", ValueError("Unsupported recovery reason")
            elif row is None:
                outcome, failure = "action_missing", ValueError("Action not found")
            elif row.phase != "DEAD":
                outcome, failure = "not_dead", ValueError("Only failed actions can be retried")
            elif row.depends_on and (parent is None or parent.phase != "DONE"):
                outcome, failure = "dependency_incomplete", ValueError("Retry and complete the dependency first")
            else:
                row.phase, row.tries, row.due, row.last_error = "READY", 0, timestamp(), ""
                row.lease, row.lease_until = "", None
                outcome = "queued"
            after = {"phase": row.phase, "tries": row.tries} if row else None
            db.add(ActionHistory(action_id=action_id, attempt=before["tries"] if before else 0,
                result="MANUAL_RETRY_REJECTED" if failure else "MANUAL_RETRY_ACCEPTED", transport="manual",
                detail={"actor": actor_detail, "reason": reason if outcome != "invalid_reason" else "invalid",
                        "outcome": outcome, "before": before, "after": after}))
        # Rejections must commit their audit before propagating the safe error.
        # An audit-write failure rolls back any queued state change atomically.
        if failure:
            raise failure
