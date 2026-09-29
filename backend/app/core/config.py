from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent  # sube hasta la raíz del repo

class Settings(BaseSettings):
    database_url: str
    google_api_key: str
    jwt_secret_key: str
    langsmith_api_key: str | None = None
    langsmith_tracing: bool = False
    langsmith_project: str = "AURA-MultiAgentes-IA"

    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8")

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        for prefijo in ("postgresql://", "postgres://"):
            if url.startswith(prefijo):
                return url.replace(prefijo, "postgresql+psycopg://", 1)
        return url

settings = Settings()