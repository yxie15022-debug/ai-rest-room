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

    # DeepSeek (OpenAI-compatible). Shared key is the fallback. Each role can
    # take its own key so welcome / plan / sleep / study / chat stay isolated.
    # Empty everywhere = LLM off; every feature falls back to fixed copy.
    deepseek_api_key: str | None = Field(default=None)
    deepseek_api_key_welcome: str | None = Field(default=None)
    deepseek_api_key_plan: str | None = Field(default=None)
    deepseek_api_key_sleep: str | None = Field(default=None)
    deepseek_api_key_study: str | None = Field(default=None)
    deepseek_api_key_chat: str | None = Field(default=None)
    deepseek_base_url: str = Field(default='https://api.deepseek.com')
    deepseek_model: str = Field(default='deepseek-chat')
    llm_timeout: float = Field(default=30.0)

    def key_for(self, role: str) -> str | None:
        """Role key first, then the shared key. Empty string means off."""
        named = {
            'welcome': self.deepseek_api_key_welcome,
            'plan': self.deepseek_api_key_plan,
            'sleep': self.deepseek_api_key_sleep,
            'study': self.deepseek_api_key_study,
            'chat': self.deepseek_api_key_chat,
        }.get(role)
        for candidate in (named, self.deepseek_api_key):
            value = (candidate or '').strip()
            if value:
                return value
        return None

    @property
    def llm_enabled(self) -> bool:
        return any(
            self.key_for(role)
            for role in ('welcome', 'plan', 'sleep', 'study', 'chat')
        )

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
