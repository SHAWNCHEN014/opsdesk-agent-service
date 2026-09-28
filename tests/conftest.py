import pytest

from opsdesk.configuration import Configuration
from opsdesk.guidance import GuidanceCatalog
from opsdesk.history import ConversationMemory
from opsdesk.retrieval import KnowledgeIndex
from opsdesk.service import SupportService
from opsdesk.storage import Database, Identity
from sqlalchemy import select


@pytest.fixture
def runtime(tmp_path):
    config = Configuration(_env_file=None, database_url="sqlite:///" + str(tmp_path / "test.db"), ledger_file=str(tmp_path / "ledger.xlsx"), vector_directory=str(tmp_path / "vectors"), model_mode="demo", action_transport="direct", worker_enabled=False, redis_url="", vector_search=False)
    db = Database(config)
    db.initialize()
    db.seed_identities(config)
    knowledge = KnowledgeIndex(db, config)
    knowledge.seed()
    memory = ConversationMemory(db, config)
    service = SupportService(db, config, knowledge, memory, GuidanceCatalog(config.skills_directory))
    with db.session() as session:
        employee = session.scalar(select(Identity).where(Identity.username == "employee")).id
        engineer = session.scalar(select(Identity).where(Identity.username == "engineer")).id
    yield config, db, knowledge, service, employee, engineer
    db.engine.dispose()
