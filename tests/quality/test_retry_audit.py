import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.exc import OperationalError

from opsdesk.main import create_app
from opsdesk.queueing import ActionWorker
from opsdesk.storage import ActionHistory, QueuedAction, timestamp
from tests.reliability.helpers import operation, snapshot


def dead_action(db, owner):
    operation(db, owner)
    with db.session.begin() as session:
        row = session.scalar(select(QueuedAction).where(QueuedAction.kind == "create_work_order"))
        row.phase, row.tries, row.last_error = "DEAD", 3, "password=synthetic-secret Bearer synthetic-token"
        return row.id


def audit_rows(db):
    with db.session() as session:
        return [{"action_id": r.action_id, "attempt": r.attempt, "result": r.result,
                 "transport": r.transport, "detail": r.detail, "created": r.created}
                for r in session.scalars(select(ActionHistory).order_by(ActionHistory.id))]


def sign_in(client, config, role):
    assert client.post("/api/login", json={"username": role, "password": getattr(config, role + "_password")}).status_code == 200


def test_authenticated_retry_records_actor_reason_time_and_preserves_history(runtime):
    config, db, _, _, owner, engineer = runtime
    action_id = dead_action(db, owner)
    with db.session.begin() as session:
        session.add(ActionHistory(action_id=action_id, attempt=3, result="FAILED", transport="direct", detail={"error": "synthetic"}))
    before = timestamp()
    app = create_app(config)
    with TestClient(app) as client:
        sign_in(client, config, "engineer")
        response = client.post(f"/api/actions/{action_id}/retry", json={"reason": "issue_resolved"})
        assert response.status_code == 200 and response.json() == {"queued": True}
        diagnostic = client.get("/api/diagnostics").json()
    rows = audit_rows(db)
    assert len(rows) == 2 and rows[0]["result"] == "FAILED"
    entry = rows[1]
    assert entry["result"] == "MANUAL_RETRY_ACCEPTED" and entry["transport"] == "manual"
    assert entry["action_id"] == action_id and entry["attempt"] == 3
    assert before <= entry["created"] <= timestamp()
    assert entry["detail"] == {"actor": {"kind": "identity", "id": engineer, "role": "engineer"},
        "reason": "issue_resolved", "outcome": "queued", "before": {"phase": "DEAD", "tries": 3},
        "after": {"phase": "READY", "tries": 0}}
    assert any(a["result"] == "MANUAL_RETRY_ACCEPTED" for a in diagnostic["audits"])
    assert "synthetic-secret" not in json.dumps(entry["detail"]) and "synthetic-token" not in json.dumps(entry["detail"])
    state = snapshot(db)
    parent = next(a for a in state["actions"] if a["id"] == action_id)
    assert parent["phase"] == "READY" and parent["tries"] == 0 and not parent["leased"]
    worker = ActionWorker(db, config)
    assert asyncio.run(worker.step()) and asyncio.run(worker.step())
    assert snapshot(db)["work_orders"] == snapshot(db)["receipts"] == 1


@pytest.mark.parametrize("role,expected", [("employee", 403), (None, 401)])
def test_employee_and_anonymous_cannot_retry(runtime, role, expected):
    config, db, _, _, owner, _ = runtime
    action_id = dead_action(db, owner)
    app = create_app(config)
    with TestClient(app) as client:
        if role: sign_in(client, config, role)
        assert client.post(f"/api/actions/{action_id}/retry").status_code == expected
    assert next(a for a in snapshot(db)["actions"] if a["id"] == action_id)["phase"] == "DEAD"
    rows = audit_rows(db)
    if role:
        assert len(rows) == 1 and rows[0]["result"] == "MANUAL_RETRY_REJECTED"
        assert rows[0]["detail"]["actor"]["id"] == owner and rows[0]["detail"]["outcome"] == "forbidden"
    else:
        assert not rows  # No attributable identity; rejected before Worker.


@pytest.mark.parametrize("scenario", ["missing", "not-dead", "dependency", "duplicate"])
def test_rejected_retries_are_audited_without_queue_mutation(runtime, scenario):
    config, db, _, _, owner, engineer = runtime
    action_id = dead_action(db, owner)
    with db.session.begin() as session:
        if scenario == "not-dead": session.get(QueuedAction, action_id).phase = "RUNNING"
        if scenario == "dependency":
            child = session.scalar(select(QueuedAction).where(QueuedAction.kind == "export_ledger"))
            child.phase = "DEAD"
            action_id = child.id
    if scenario == "missing": action_id = "nonexistent"
    app = create_app(config)
    with TestClient(app) as client:
        sign_in(client, config, "engineer")
        if scenario == "duplicate": assert client.post(f"/api/actions/{action_id}/retry").status_code == 200
        before = snapshot(db)["actions"]
        assert client.post(f"/api/actions/{action_id}/retry", json={"reason": "dependency_restored"}).status_code == 409
    assert snapshot(db)["actions"] == before
    row = audit_rows(db)[-1]
    assert row["result"] == "MANUAL_RETRY_REJECTED" and row["action_id"] == action_id
    assert row["detail"]["actor"]["id"] == engineer
    assert row["detail"]["outcome"] == {"missing": "action_missing", "not-dead": "not_dead", "dependency": "dependency_incomplete", "duplicate": "not_dead"}[scenario]
    assert row["detail"]["before"] == row["detail"]["after"]


@pytest.mark.parametrize("body", [{"reason": "password=synthetic-secret token=synthetic-token"},
    {"reason": "issue_resolved", "actor_id": "spoofed"}])
def test_retry_reason_and_actor_input_are_restricted(runtime, body):
    config, db, _, _, owner, _ = runtime
    action_id = dead_action(db, owner)
    with TestClient(create_app(config)) as client:
        sign_in(client, config, "engineer")
        assert client.post(f"/api/actions/{action_id}/retry", json=body).status_code == 422
    assert not audit_rows(db)
    assert next(a for a in snapshot(db)["actions"] if a["id"] == action_id)["phase"] == "DEAD"


def test_retry_audit_write_failure_rolls_back_action(runtime):
    config, db, _, _, owner, _ = runtime
    action_id = dead_action(db, owner)
    app = create_app(config)
    def fail_audit(session, *_):
        if any(isinstance(row, ActionHistory) for row in session.new):
            raise OperationalError("synthetic", None, ValueError("password=synthetic-secret token=synthetic-token"))
    with TestClient(app, raise_server_exceptions=False) as client:
        sign_in(client, config, "engineer")
        event.listen(app.state.database.session, "before_flush", fail_audit)
        try: response = client.post(f"/api/actions/{action_id}/retry")
        finally: event.remove(app.state.database.session, "before_flush", fail_audit)
    assert response.status_code == 503 and response.json()["detail"] == "Recovery audit unavailable; action unchanged"
    assert "synthetic-secret" not in response.text and "synthetic-token" not in response.text
    assert not audit_rows(db)
    parent = next(a for a in snapshot(db)["actions"] if a["id"] == action_id)
    assert parent["phase"] == "DEAD" and parent["tries"] == 3


def test_trusted_internal_retry_is_explicitly_system_not_fake_engineer(runtime):
    config, db, _, _, owner, _ = runtime
    action_id = dead_action(db, owner)
    ActionWorker(db, config).retry(action_id)
    rows = audit_rows(db)
    assert len(rows) == 1 and rows[0]["detail"]["actor"] == {"kind": "system", "id": None, "role": None}
