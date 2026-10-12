import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from opsdesk.main import create_app


@pytest.mark.parametrize("failure", ["connection", "query"])
def test_health_database_failure_is_safe_structured_503(runtime, monkeypatch, failure):
    app = create_app(runtime[0])
    error = OperationalError("synthetic SELECT", None, ValueError("password=synthetic-private-token"))
    def broken(*_): raise error
    with TestClient(app, raise_server_exceptions=False) as client:
        if failure == "connection":
            monkeypatch.setattr(app.state.database, "session", broken)
        else:
            event.listen(app.state.database.engine, "before_cursor_execute", broken)
        try: response = client.get("/api/health")
        finally:
            if failure == "query": event.remove(app.state.database.engine, "before_cursor_execute", broken)
        assert response.status_code == 503
        payload = response.json()
        assert payload["status"] == "degraded" and payload["database"] == {"status": "unavailable", "error": "OperationalError"}
        assert "synthetic-private-token" not in response.text and "synthetic SELECT" not in response.text
    client.close()


def test_health_database_recovers_and_worker_disabled_is_valid(runtime):
    app = create_app(runtime[0])
    def broken(*_): raise OperationalError("synthetic", None, ValueError("private"))
    with TestClient(app, raise_server_exceptions=False) as client:
        event.listen(app.state.database.engine, "before_cursor_execute", broken)
        try: assert client.get("/api/health").status_code == 503
        finally: event.remove(app.state.database.engine, "before_cursor_execute", broken)
        response = client.get("/api/health")
        assert response.status_code == 200 and response.json()["database"] == {"status": "ok"}
        assert response.json()["worker"]["enabled"] is False
