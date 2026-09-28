import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy import select, text, update

from opsdesk.configuration import PROJECT, Configuration
from opsdesk.contracts import SignInInput, SupportInput, WorkOrderUpdate
from opsdesk.guidance import GuidanceCatalog
from opsdesk.history import ConversationMemory
from opsdesk.identity import Authentication
from opsdesk.queueing import ActionWorker
from opsdesk.redaction import clean_text
from opsdesk.retrieval import KnowledgeIndex
from opsdesk.service import SupportService
from opsdesk.storage import ActionHistory, Database, DeliveryReceipt, QueuedAction, SupportRequest, WorkOrder, timestamp


def create_app(config=None):
    config = config or Configuration()
    database = Database(config)
    auth = Authentication(database, config)
    knowledge = KnowledgeIndex(database, config)
    memory = ConversationMemory(database, config)
    guidance = GuidanceCatalog(config.skills_directory)
    service = SupportService(database, config, knowledge, memory, guidance)
    worker = ActionWorker(database, config)
    origin = urlparse(config.origin)
    allowed_hosts = [origin.netloc, "127.0.0.1:*", "localhost:*", "testserver"]
    public_mcp = FastMCP("OpsDesk external assistant", instructions="Submit IT support and inspect only the authenticated user's own operations. This server is used by a simulated Alexa+ assistant, not an official Alexa integration.", streamable_http_path="/", stateless_http=True, json_response=True, transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=allowed_hosts, allowed_origins=[config.origin]))

    def account(request: Request):
        return auth.resolve(request.cookies)

    def engineer(user=Depends(account)):
        if user.role != "engineer":
            raise HTTPException(403, "Engineer role required")
        return user

    def tool_identity(ctx):
        request = ctx.request_context.request
        if request is None:
            raise ValueError("Authenticated HTTP context is required")
        return auth.resolve(request.cookies, request.headers.get("authorization", ""))

    @public_mcp.tool()
    async def support_request(message: str, request_id: str, ctx: Context, thread_id: str | None = None) -> dict:
        """Queue an IT question or incident. Use a stable unique request ID to retry safely."""
        user = tool_identity(ctx)
        return await service.submit(user.id, SupportInput(message=message, request_id=request_id, thread_id=thread_id), "external-mcp")

    @public_mcp.tool()
    async def request_status(operation_id: str, ctx: Context) -> dict:
        """Read a previously submitted operation owned by the authenticated user."""
        user = tool_identity(ctx)
        return service.status(operation_id, user.id)

    mcp_app = public_mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app):
        database.initialize()
        database.seed_identities(config)
        service.recover()
        knowledge.seed()
        if config.vector_search:
            await knowledge.restore_vectors()
        async with public_mcp.session_manager.run():
            job = asyncio.create_task(worker.run()) if config.worker_enabled else None
            yield
            await service.close()
            worker.stopping = True
            if job:
                job.cancel()
                await asyncio.gather(job, return_exceptions=True)
        database.engine.dispose()

    app = FastAPI(title="OpsDesk independent service desk", version="1.0.0", lifespan=lifespan)
    app.state.config, app.state.database, app.state.service = config, database, service
    app.state.knowledge, app.state.worker = knowledge, worker

    @app.middleware("http")
    async def boundary(request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        if host not in {origin.hostname, "127.0.0.1", "localhost", "testserver"}:
            return JSONResponse({"detail": "Host is not allowed"}, 400)
        supplied_origin = request.headers.get("origin")
        if supplied_origin and supplied_origin != config.origin:
            return JSONResponse({"detail": "Origin is not allowed"}, 403)
        if request.url.path.startswith("/mcp"):
            try:
                auth.resolve(request.cookies, request.headers.get("authorization", ""))
            except HTTPException as exc:
                return JSONResponse({"detail": exc.detail}, exc.status_code)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store" if request.url.path.startswith(("/api", "/mcp")) else "no-cache"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
        return response

    @app.get("/api/health")
    def health():
        with database.session() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ok", "project": "OpsDesk", "model_mode": config.model_mode}

    @app.post("/api/login")
    def login(body: SignInInput, response: Response):
        token, user = auth.sign_in(body.username, body.password)
        response.set_cookie("opsdesk_session", token, max_age=43200, httponly=True, samesite="strict", secure=config.origin.startswith("https://"))
        return user

    @app.post("/api/logout")
    def logout(request: Request, response: Response):
        auth.revoke(request.cookies.get("opsdesk_session", ""))
        response.delete_cookie("opsdesk_session")
        return {"signed_out": True}

    @app.get("/api/me")
    def me(user=Depends(account)):
        return {"username": user.username, "role": user.role, "model_mode": config.model_mode}

    @app.post("/api/support")
    async def submit(body: SupportInput, user=Depends(account)):
        return await service.submit(user.id, body)

    @app.get("/api/operations/{operation_id}")
    def status(operation_id: str, user=Depends(account)):
        return service.status(operation_id, user.id, user.role == "engineer")

    @app.get("/api/operations/{operation_id}/events")
    async def events(operation_id: str, request: Request, user=Depends(account)):
        service.status(operation_id, user.id, user.role == "engineer")

        async def generate():
            cursor, ticks = 0, 0
            while not await request.is_disconnected():
                state = service.status(operation_id, user.id, user.role == "engineer")
                for event in state["events"][cursor:]:
                    yield "event: progress\ndata: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                cursor = len(state["events"])
                if state["phase"] != "RUNNING":
                    # Only reviewed text is released; these are display chunks, not raw model tokens.
                    answer = state["outcome"].get("answer", "")
                    for offset in range(0, len(answer), 60):
                        yield "event: answer\ndata: " + json.dumps({"text": answer[offset:offset + 60]}, ensure_ascii=False) + "\n\n"
                    yield "event: complete\ndata: " + json.dumps(state, ensure_ascii=False) + "\n\n"
                    break
                ticks += 1
                if ticks % 30 == 0:
                    yield ": heartbeat\n\n"
                await asyncio.sleep(0.5)
        return StreamingResponse(generate(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})

    async def mcp_call(request, tool, arguments):
        headers = {"Cookie": "opsdesk_session=" + request.cookies.get("opsdesk_session", "")}
        async with httpx.AsyncClient(headers=headers, timeout=20) as client:
            endpoint = (config.mcp_client_url or config.origin).rstrip("/") + "/mcp/"
            async with streamable_http_client(endpoint, http_client=client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    initialized = await session.initialize()
                    result = await session.call_tool(tool, arguments)
                    if result.isError:
                        raise HTTPException(502, "External MCP tool rejected the request")
                    output = result.structuredContent or json.loads(next(part.text for part in result.content if part.type == "text"))
                    return {"protocol": initialized.protocolVersion, "transport": "Streamable HTTP", "tool": tool, "result": output}

    @app.post("/api/simulated-assistant")
    async def simulated(body: SupportInput, request: Request, user=Depends(account)):
        return await mcp_call(request, "support_request", body.model_dump(exclude_none=True))

    @app.get("/api/simulated-assistant/{operation_id}")
    async def simulated_status(operation_id: str, request: Request, user=Depends(account)):
        return await mcp_call(request, "request_status", {"operation_id": operation_id})

    @app.get("/api/tickets")
    def tickets(user=Depends(account)):
        with database.session() as db:
            query = select(WorkOrder, SupportRequest).join(SupportRequest, WorkOrder.request_id == SupportRequest.id).order_by(WorkOrder.created.desc()).limit(100)
            if user.role != "engineer":
                query = query.where(SupportRequest.owner == user.id)
            return [{"id": order.id, "reference": order.reference, "phase": order.phase, "revision": order.revision, "assignee": order.assignee, "notes": order.notes, "created": order.created.isoformat(), "operation_id": request.id, "summary": request.outcome["intake"]["summary"], "priority": request.outcome["priority"]["level"], "category": request.outcome["intake"]["category"]} for order, request in db.execute(query)]

    @app.patch("/api/tickets/{ticket_id}")
    def update_ticket(ticket_id: str, body: WorkOrderUpdate, user=Depends(engineer)):
        with database.session.begin() as db:
            row = db.get(WorkOrder, ticket_id)
            if row is None:
                raise HTTPException(404, "Ticket not found")
            if row.phase == "RESOLVED":
                raise HTTPException(409, "Resolved tickets cannot be edited")
            notes = [*row.notes, {"author": user.username, "text": clean_text(body.note), "at": timestamp().isoformat(), "phase": body.phase}]
            changed = db.execute(update(WorkOrder).where(WorkOrder.id == ticket_id, WorkOrder.revision == body.expected_revision, WorkOrder.phase != "RESOLVED").values(phase=body.phase, assignee=user.username, notes=notes, revision=WorkOrder.revision + 1))
            if not changed.rowcount:
                raise HTTPException(409, "Ticket changed; refresh before editing")
        return {"updated": True}

    @app.get("/api/diagnostics")
    def diagnostics(user=Depends(engineer)):
        redis_ok = False
        if memory.cache is not None:
            try:
                redis_ok = bool(memory.cache.ping())
            except Exception:
                pass
        with database.session() as db:
            actions = list(db.scalars(select(QueuedAction).order_by(QueuedAction.due.desc()).limit(30)))
            audits = list(db.scalars(select(ActionHistory).order_by(ActionHistory.id.desc()).limit(30)))
            receipts = list(db.scalars(select(DeliveryReceipt).order_by(DeliveryReceipt.created.desc()).limit(20)))
            return {"database": database.engine.dialect.name, "redis": redis_ok, "memory": memory.observations, "model_mode": config.model_mode, "model": config.model_name, "vector": knowledge.vector_state, "segments": len(knowledge.rows()), "skills": guidance.describe(), "actions": [{"id": job.id, "kind": job.kind, "phase": job.phase, "tries": job.tries, "error": job.last_error} for job in actions], "audits": [{"action_id": item.action_id, "attempt": item.attempt, "result": item.result, "transport": item.transport, "detail": item.detail} for item in audits], "receipts": [{"kind": item.kind, "detail": item.detail} for item in receipts], "mcp": {"endpoint": "/mcp/", "simulation": True}}

    @app.post("/api/actions/{action_id}/retry")
    def retry(action_id: str, user=Depends(engineer)):
        try:
            worker.retry(action_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        return {"queued": True}

    @app.get("/api/knowledge")
    def documents(user=Depends(engineer)):
        counts = {}
        for row in knowledge.rows():
            counts[row.source] = counts.get(row.source, 0) + 1
        return {"documents": counts, "vector": knowledge.vector_state}

    @app.post("/api/knowledge")
    async def import_document(file: UploadFile, user=Depends(engineer)):
        data = await file.read(2_000_001)
        if len(data) > 2_000_000:
            raise HTTPException(413, "Document must be under 2 MB")
        try:
            count = knowledge.import_bytes(file.filename or "document.txt", data)
        except (ValueError, UnicodeError) as exc:
            raise HTTPException(422, str(exc))
        return {"segments": count, "rebuild_required": config.vector_search}

    @app.post("/api/knowledge/rebuild")
    async def rebuild(user=Depends(engineer)):
        try:
            await knowledge.rebuild_vectors()
        except Exception as exc:
            raise HTTPException(503, "Embedding rebuild failed: " + type(exc).__name__)
        return knowledge.vector_state

    @app.get("/api/ledger")
    def ledger(user=Depends(engineer)):
        if not Path(config.ledger_file).exists():
            raise HTTPException(404, "No ledger has been exported yet")
        return FileResponse(config.ledger_file, filename="opsdesk-it-ledger.xlsx")

    app.mount("/mcp", mcp_app)
    app.mount("/", StaticFiles(directory=PROJECT / "web", html=True), name="web")
    return app


app = create_app()
