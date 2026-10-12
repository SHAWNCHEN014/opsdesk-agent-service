from datetime import timedelta

from sqlalchemy import func, select

from opsdesk.queueing import enqueue
from opsdesk.storage import ActionHistory, DeliveryReceipt, QueuedAction, SupportRequest, Thread, WorkOrder, new_id, timestamp


def operation(db, owner, priority="P2"):
    request_id, thread = new_id(), new_id()
    with db.session.begin() as session:
        session.add(Thread(id=thread, owner=owner))
        session.flush()
        session.add(SupportRequest(id=request_id, owner=owner, thread_id=thread, client_key=request_id,
            input_digest="synthetic", message="电脑无法开机", phase="COMPLETE",
            outcome={"intake": {"intent": "INCIDENT", "summary": "电脑无法开机"}, "priority": {"level": priority}}))
        session.flush()
        enqueue(session, request_id, priority)
    return request_id


def snapshot(db):
    with db.session() as session:
        actions = list(session.scalars(select(QueuedAction).order_by(QueuedAction.id)))
        audits = list(session.scalars(select(ActionHistory).order_by(ActionHistory.id)))
        return {"actions": [{"id": a.id, "kind": a.kind, "phase": a.phase, "tries": a.tries, "leased": bool(a.lease), "error": a.last_error} for a in actions],
            "work_orders": session.scalar(select(func.count()).select_from(WorkOrder)),
            "receipts": session.scalar(select(func.count()).select_from(DeliveryReceipt)),
            "audits": [{"action": a.action_id, "attempt": a.attempt, "result": a.result} for a in audits]}


class Clock:
    def __init__(self):
        self.now = timestamp() + timedelta(seconds=1)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


def stop_after_terminal(worker, db, monkeypatch):
    finish = worker.finish

    def wrapped(*args, **kwargs):
        result = finish(*args, **kwargs)
        if all(a["phase"] in {"DONE", "DEAD"} for a in snapshot(db)["actions"]):
            worker.stopping = True
        return result
    monkeypatch.setattr(worker, "finish", wrapped)
