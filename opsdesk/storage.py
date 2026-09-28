from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, event, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def timestamp():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id():
    return uuid4().hex


class Tables(DeclarativeBase):
    pass


class Identity(Tables):
    __tablename__ = "identities"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(20), default="employee")


class AccessGrant(Tables):
    __tablename__ = "access_grants"
    token_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    identity_id: Mapped[str] = mapped_column(ForeignKey("identities.id"))
    expires: Mapped[datetime] = mapped_column(DateTime)


class Thread(Tables):
    __tablename__ = "threads"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner: Mapped[str] = mapped_column(ForeignKey("identities.id"), index=True)
    created: Mapped[datetime] = mapped_column(DateTime, default=timestamp)


class Entry(Tables):
    __tablename__ = "entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(ForeignKey("threads.id"), index=True)
    speaker: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    created: Mapped[datetime] = mapped_column(DateTime, default=timestamp)


class SupportRequest(Tables):
    __tablename__ = "service_requests"
    __table_args__ = (UniqueConstraint("owner", "client_key", name="request_dedup"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner: Mapped[str] = mapped_column(ForeignKey("identities.id"), index=True)
    thread_id: Mapped[str] = mapped_column(ForeignKey("threads.id"))
    client_key: Mapped[str] = mapped_column(String(100))
    input_digest: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(32), default="web")
    phase: Mapped[str] = mapped_column(String(24), default="RUNNING")
    outcome: Mapped[dict] = mapped_column(JSON, default=dict)
    events: Mapped[list] = mapped_column(JSON, default=list)
    created: Mapped[datetime] = mapped_column(DateTime, default=timestamp)


class WorkOrder(Tables):
    __tablename__ = "work_orders"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    reference: Mapped[str] = mapped_column(String(20), unique=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("service_requests.id"), unique=True)
    phase: Mapped[str] = mapped_column(String(24), default="OPEN")
    assignee: Mapped[str] = mapped_column(String(80), default="")
    notes: Mapped[list] = mapped_column(JSON, default=list)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[datetime] = mapped_column(DateTime, default=timestamp)


class QueuedAction(Tables):
    __tablename__ = "action_queue"
    __table_args__ = (UniqueConstraint("request_id", "kind", name="action_dedup"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(ForeignKey("service_requests.id"))
    kind: Mapped[str] = mapped_column(String(32))
    depends_on: Mapped[str | None] = mapped_column(ForeignKey("action_queue.id"), nullable=True)
    phase: Mapped[str] = mapped_column(String(24), default="READY", index=True)
    tries: Mapped[int] = mapped_column(Integer, default=0)
    due: Mapped[datetime] = mapped_column(DateTime, default=timestamp)
    lease: Mapped[str] = mapped_column(String(32), default="")
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")


class ActionHistory(Tables):
    __tablename__ = "action_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action_id: Mapped[str] = mapped_column(String(32), index=True)
    attempt: Mapped[int] = mapped_column(Integer)
    result: Mapped[str] = mapped_column(String(24))
    transport: Mapped[str] = mapped_column(String(16))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created: Mapped[datetime] = mapped_column(DateTime, default=timestamp)


class DeliveryReceipt(Tables):
    __tablename__ = "delivery_receipts"
    __table_args__ = (UniqueConstraint("request_id", "kind", name="receipt_dedup"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(ForeignKey("service_requests.id"))
    kind: Mapped[str] = mapped_column(String(32))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created: Mapped[datetime] = mapped_column(DateTime, default=timestamp)


class DocumentSegment(Tables):
    __tablename__ = "document_segments"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(160), index=True)
    title: Mapped[str] = mapped_column(String(160))
    text: Mapped[str] = mapped_column(Text)


class Database:
    def __init__(self, config):
        config.ensure_directories()
        options = {"connect_args": {"check_same_thread": False, "timeout": 30}} if config.database_url.startswith("sqlite") else {"pool_pre_ping": True}
        self.engine = create_engine(config.database_url, **options)
        if config.database_url.startswith("sqlite"):
            @event.listens_for(self.engine, "connect")
            def sqlite_settings(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA journal_mode=WAL")
        self.session = sessionmaker(self.engine, expire_on_commit=False)

    def initialize(self):
        Tables.metadata.create_all(self.engine)

    def seed_identities(self, config):
        from opsdesk.identity import encode_password
        with self.session.begin() as db:
            for username, role, password in [("employee", "employee", config.employee_password), ("engineer", "engineer", config.engineer_password)]:
                if db.scalar(select(Identity).where(Identity.username == username)) is None:
                    db.add(Identity(username=username, role=role, password=encode_password(password)))
