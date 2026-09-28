"""Exercise a running service, including real HTTP MCP and queued stdio tools."""
import argparse
import asyncio
import json
from pathlib import Path
import time
from uuid import uuid4

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def verify(base, output, require_real):
    started = time.monotonic()
    report = {"base": base, "started_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), "scenarios": []}
    async with httpx.AsyncClient(base_url=base, timeout=180) as client:
        for _ in range(30):
            try:
                health = await client.get("/api/health", timeout=2)
                if health.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
        else:
            raise RuntimeError("Service did not become healthy within 30 seconds")
        response = await client.post("/api/login", json={"username": "employee", "password": "local-demo-only"})
        response.raise_for_status()
        cases = [("如何申请业务系统访问权限？", "FAQ", "P3", "web"), ("我的电脑无法开机，只有我受影响。", "INCIDENT", "P2", "web"), ("全员无法访问核心业务系统，服务中断。", "INCIDENT", "P1", "mcp")]
        thread = None
        for message, intent, priority, transport in cases:
            tick = time.monotonic()
            payload = {"message": message, "request_id": uuid4().hex, **({"thread_id": thread} if thread else {})}
            if transport == "web":
                response = await client.post("/api/support", json=payload)
                response.raise_for_status()
                receipt = response.json()
                protocol = None
            else:
                async with streamable_http_client(base + "/mcp/", http_client=client) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        handshake = await session.initialize()
                        protocol = handshake.protocolVersion
                        catalog = await session.list_tools()
                        assert {tool.name for tool in catalog.tools} == {"support_request", "request_status"}
                        result = await session.call_tool("support_request", payload)
                        assert not result.isError, result
                        receipt = result.structuredContent or json.loads(next(part.text for part in result.content if part.type == "text"))
                        assert receipt
            thread = receipt["thread_id"]
            for _ in range(360):
                response = await client.get("/api/operations/" + receipt["operation_id"])
                response.raise_for_status()
                state = response.json()
                if state["phase"] != "RUNNING":
                    break
                await asyncio.sleep(1)
            assert state["phase"] == "COMPLETE", state
            outcome = state["outcome"]
            assert (outcome["intake"]["intent"], outcome["priority"]["level"]) == (intent, priority), outcome
            assert outcome["answer"] and outcome["evidence"]
            if require_real:
                assert outcome["model_mode"] == "ollama" and not outcome["degraded"], outcome
                assert len(outcome["model_calls"]) == 4 and all(item["success"] for item in outcome["model_calls"])
                assert any("vector" in item["channels"] for item in outcome["evidence"])
            replay = await client.post("/api/support", json=payload)
            assert replay.json()["operation_id"] == receipt["operation_id"] and replay.json()["reused"]
            if transport == "mcp":
                response = await client.get("/api/simulated-assistant/" + receipt["operation_id"])
                response.raise_for_status()
                assert response.json()["result"]["phase"] == "COMPLETE"
            entry = {"operation_id": receipt["operation_id"], "intent": intent, "priority": priority, "transport": transport, "protocol": protocol, "duration_ms": round((time.monotonic() - tick) * 1000), "outcome": outcome}
            report["scenarios"].append(entry)
            print(json.dumps({key: entry[key] for key in ("intent", "priority", "transport", "protocol", "duration_ms")}), flush=True)
        for _ in range(90):
            tickets = (await client.get("/api/tickets")).json()
            if all(any(ticket["operation_id"] == entry["operation_id"] for ticket in tickets) for entry in report["scenarios"] if entry["intent"] != "FAQ"):
                break
            await asyncio.sleep(1)
        selected = [ticket for ticket in tickets if ticket["operation_id"] in {entry["operation_id"] for entry in report["scenarios"]}]
        assert len(selected) == 2
        response = await client.post("/api/login", json={"username": "engineer", "password": "engineer-demo-only"})
        response.raise_for_status()
        ticket = next(ticket for ticket in selected if ticket["priority"] == "P2")
        payload = {"phase": "INVESTIGATING", "note": "检查批准的电源连接，准备替换电源适配器。 / Checked approved power connections.", "expected_revision": ticket["revision"]}
        assert (await client.patch("/api/tickets/" + ticket["id"], json=payload)).status_code == 200
        payload.update(phase="RESOLVED", note="更换适配器后设备恢复，已确认正常开机。 / Replaced adapter and verified startup.", expected_revision=ticket["revision"] + 1)
        assert (await client.patch("/api/tickets/" + ticket["id"], json=payload)).status_code == 200
        await client.post("/api/login", json={"username": "employee", "password": "local-demo-only"})
        external_status = await client.get("/api/simulated-assistant/" + ticket["operation_id"])
        external_status.raise_for_status()
        assert external_status.json()["result"]["ticket"]["phase"] == "RESOLVED"
        await client.post("/api/login", json={"username": "engineer", "password": "engineer-demo-only"})
        for _ in range(90):
            diagnostics = (await client.get("/api/diagnostics")).json()
            states = [(await client.get("/api/operations/" + entry["operation_id"])).json() for entry in report["scenarios"]]
            if all(action["phase"] == "DONE" for state in states for action in state["actions"]):
                break
            await asyncio.sleep(1)
        assert all(action["phase"] == "DONE" for state in states for action in state["actions"]), states
        assert any(item["kind"] == "escalation" and item["detail"]["mode"] == "record" for item in diagnostics["receipts"])
        assert any(item["transport"] == "mcp" and item["result"] == "DONE" for item in diagnostics["audits"])
        ledger = await client.get("/api/ledger")
        assert ledger.status_code == 200 and ledger.content.startswith(b"PK")
        if require_real:
            assert diagnostics["database"] == "mysql" and diagnostics["redis"] and diagnostics["memory"]["hits"] >= 1
        report["runtime"] = diagnostics
        report["work_orders"] = selected
        report["total_seconds"] = round(time.monotonic() - started, 2)
        report["passed"] = True
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Live workflow verification passed: " + output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8085")
    parser.add_argument("--output", default="artifacts/live-verification.json")
    parser.add_argument("--require-real", action="store_true")
    args = parser.parse_args()
    asyncio.run(verify(args.base, args.output, args.require_real))
