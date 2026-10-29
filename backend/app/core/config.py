from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent  # sube hasta la raíz del repo

class Settings(BaseSettings):
    database_url: str
    google_api_key: str | None = None
    langsmith_api_key: str | None = None
    langsmith_tracing: bool = False
    langsmith_project: str = "AURA-MultiAgentes-IA"
    seed_password: str | None = None
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8")
    jwt_secret: str                  # sin default: si falta, la app no arranca
    jwt_algoritmo: str = "HS256"
    jwt_expira_minutos: int = 60
    idempotencia_ttl_horas: int = 24

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        for prefijo in ("postgresql://", "postgres://"):
            if url.startswith(prefijo):
                return url.replace(prefijo, "postgresql+psycopg://", 1)
        return url

settings = Settings()