from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / 'data'


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = Field(default='ai-rest-room')
    mcp_host: str = Field(default='127.0.0.1')
    mcp_port: int = Field(default=8001)

    # Local SQLite by default. No Postgres required for v1.
    database_url: str = Field(default=f'sqlite:///{(DATA_DIR / "rest_room.db").as_posix()}')
    public_base_url: str = Field(default='http://127.0.0.1:8000')
    mcp_public_url: str = Field(default='http://127.0.0.1:8001/mcp')
    mcp_allowed_hosts: str | None = Field(default=None)

    reports_dir: str = Field(default=str(DATA_DIR / 'reports'))

    # Optional. Empty = open door (connection is identity).
    api_key: str | None = Field(default=None)
    allowed_origins: str = Field(
        default=(
            'http://127.0.0.1:8000,http://localhost:8000,'
            'http://127.0.0.1:8001,http://localhost:8001,'
            'https://chat.openai.com,https://chatgpt.com,https://claude.ai'
        )
    )

    # DeepSeek (OpenAI-compatible). Empty key = LLM off, every feature falls back
    # to the deterministic copy. Used by enter pace, sleep, study and chat.
    deepseek_api_key: str | None = Field(default=None)
    deepseek_base_url: str = Field(default='https://api.deepseek.com')
    deepseek_model: str = Field(default='deepseek-chat')
    llm_timeout: float = Field(default=30.0)

    @property
    def llm_enabled(self) -> bool:
        return bool((self.deepseek_api_key or '').strip())

    @property
    def allowed_origins_list(self) -> list[str]:
        values = [item.strip().rstrip('/') for item in self.allowed_origins.split(',') if item.strip()]
        deduped: list[str] = []
        for item in values:
            if item not in deduped:
                deduped.append(item)
        return deduped

    @property
    def mcp_allowed_hosts_list(self) -> list[str]:
        raw_values: list[str] = []
        if self.mcp_allowed_hosts:
            raw_values.extend(item.strip() for item in self.mcp_allowed_hosts.split(',') if item.strip())

        parsed = urlparse(self.mcp_public_url)
        netloc = parsed.netloc.strip()
        hostname = (parsed.hostname or '').strip()
        if netloc:
            raw_values.append(netloc)
        if hostname:
            raw_values.append(hostname)
            raw_values.append(f'{hostname}:*')

        raw_values.extend(['127.0.0.1:*', 'localhost:*', '[::1]:*'])

        deduped: list[str] = []
        for item in raw_values:
            if item and item not in deduped:
                deduped.append(item)
        return deduped

    @property
    def reports_path(self) -> Path:
        return Path(self.reports_dir)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    settings.reports_path.mkdir(parents=True, exist_ok=True)
    return settings
