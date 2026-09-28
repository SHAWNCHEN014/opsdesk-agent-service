from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT = Path(__file__).resolve().parent.parent


class Configuration(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPSDESK_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./var/service.db"
    redis_url: str = ""
    model_mode: str = "demo"
    model_name: str = "qwen3:8b"
    ollama_url: str = "http://127.0.0.1:11434"
    model_timeout: float = 120
    vector_search: bool = False
    embed_model: str = "nomic-embed-text-v2-moe"
    vector_directory: str = "./var/vectors"
    ledger_file: str = "./var/it-ledger.xlsx"
    origin: str = "http://127.0.0.1:8085"
    mcp_token: str = "local-mcp-demo"
    employee_password: str = "local-demo-only"
    engineer_password: str = "engineer-demo-only"
    worker_enabled: bool = True
    action_transport: str = "mcp"
    max_action_attempts: int = 3
    notification_mode: str = "record"
    notification_limit: int = 30
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_sender: str = ""
    smtp_recipient: str = ""
    knowledge_directory: Path = PROJECT / "knowledge"
    skills_directory: Path = PROJECT / "skills"

    def ensure_directories(self):
        Path(self.ledger_file).parent.mkdir(parents=True, exist_ok=True)
        Path(self.vector_directory).parent.mkdir(parents=True, exist_ok=True)
        if self.database_url.startswith("sqlite:///"):
            Path(self.database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
