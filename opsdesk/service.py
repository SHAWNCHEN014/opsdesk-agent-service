import asyncio
import hashlib
import logging

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from opsdesk.inference import InferenceGateway
from opsdesk.orchestration import ServiceTeam
from opsdesk.queueing import enqueue
from opsdesk.redaction import clean_text
from opsdesk.storage import Entry, QueuedAction, SupportRequest, Thread, WorkOrder, new_id


def redact_tree(value):
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, list):
        return [redact_tree(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_tree(item) for key, item in value.items()}
    return value


class SupportService:
    def __init__(self, database, config, knowledge, memory, guidance):
        self.database, self.config = database, config
        self.knowledge, self.memory, self.guidance = knowledge, memory, guidance
        self.tasks, self.thread_locks, self.live_events = {}, {}, {}

    def recover(self):
        with self.database.session.begin() as db:
            db.execute(update(SupportRequest).where(SupportRequest.phase == "RUNNING").values(phase="FAILED", outcome={"error": "Service restarted during processing. Submit again with a new request ID."}))

    async def submit(self, owner, body, origin="web"):
        message = clean_text(body.message)
        if not message:
            raise HTTPException(422, "Message is empty")
        digest = hashlib.sha256((body.message + "\0" + (body.thread_id or "")).encode()).hexdigest()
        try:
            with self.database.session.begin() as db:
                previous = db.scalar(select(SupportRequest).where(SupportRequest.owner == owner, SupportRequest.client_key == body.request_id))
                if previous:
                    if previous.input_digest != digest:
                        raise HTTPException(409, "Request ID was already used for different input")
                    return {"operation_id": previous.id, "thread_id": previous.thread_id, "reused": True}
                if body.thread_id:
                    thread = db.get(Thread, body.thread_id)
                    if thread is None or thread.owner != owner:
                        raise HTTPException(404, "Thread not found")
                else:
                    thread = Thread(id=new_id(), owner=owner)
                    db.add(thread)
                    db.flush()
                row = SupportRequest(id=new_id(), owner=owner, thread_id=thread.id, client_key=body.request_id, input_digest=digest, message=message, origin=origin)
                db.add(row)
                db.flush()
                operation_id, thread_id = row.id, thread.id
        except IntegrityError:
            # A concurrent identical submission may have won the unique constraint.
            with self.database.session() as db:
                previous = db.scalar(select(SupportRequest).where(SupportRequest.owner == owner, SupportRequest.client_key == body.request_id))
                if previous is None or previous.input_digest != digest:
                    raise HTTPException(409, "Conflicting request ID")
                return {"operation_id": previous.id, "thread_id": previous.thread_id, "reused": True}
        self.live_events[operation_id] = []
        task = asyncio.create_task(self._process(operation_id, owner, thread_id, message))
        self.tasks[operation_id] = task
        task.add_done_callback(lambda _: self.tasks.pop(operation_id, None))
        return {"operation_id": operation_id, "thread_id": thread_id, "reused": False}

    async def _process(self, operation_id, owner, thread_id, message):
        async def emit(event):
            self.live_events[operation_id].append(event)

        lock = self.thread_locks.setdefault(thread_id, asyncio.Lock())
        try:
            async with lock:
                # Recall happens before appending the current message, avoiding duplicate context.
                team = ServiceTeam(InferenceGateway(self.config), self.knowledge, self.memory, self.guidance)
                outcome = redact_tree(await team.solve(owner, thread_id, message, emit))
                with self.database.session.begin() as db:
                    row = db.get(SupportRequest, operation_id)
                    row.phase, row.outcome, row.events = "COMPLETE", outcome, list(self.live_events[operation_id])
                    db.add_all([Entry(thread_id=thread_id, speaker="user", text=message), Entry(thread_id=thread_id, speaker="assistant", text=outcome["answer"])])
                    if outcome["intake"]["intent"] != "FAQ":
                        enqueue(db, operation_id, outcome["priority"]["level"])
                self.memory.refresh(owner, thread_id)
        except asyncio.CancelledError:
            self._failed(operation_id, "Service stopped during processing")
            raise
        except Exception as exc:
            logging.exception("Support operation failed: %s", operation_id)
            self._failed(operation_id, "Processing failed: " + type(exc).__name__)
        finally:
            self.live_events.pop(operation_id, None)
            if not lock.locked():
                # Locks are retained while queued calls still use this thread.
                if not getattr(lock, "_waiters", None):
                    self.thread_locks.pop(thread_id, None)

    def _failed(self, operation_id, reason):
        with self.database.session.begin() as db:
            row = db.get(SupportRequest, operation_id)
            row.phase, row.outcome, row.events = "FAILED", {"error": reason}, list(self.live_events.get(operation_id, []))

    def status(self, operation_id, owner, engineer=False):
        with self.database.session() as db:
            row = db.get(SupportRequest, operation_id)
            if row is None or (row.owner != owner and not engineer):
                raise HTTPException(404, "Operation not found")
            order = db.scalar(select(WorkOrder).where(WorkOrder.request_id == operation_id))
            actions = list(db.scalars(select(QueuedAction).where(QueuedAction.request_id == operation_id)))
            return {"operation_id": row.id, "thread_id": row.thread_id, "phase": row.phase, "outcome": row.outcome, "events": list(self.live_events.get(operation_id, row.events)), "work_order": order.reference if order else None, "ticket": {"reference": order.reference, "phase": order.phase, "assignee": order.assignee, "notes": order.notes, "revision": order.revision} if order else None, "actions": [{"kind": job.kind, "phase": job.phase, "tries": job.tries} for job in actions]}

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
