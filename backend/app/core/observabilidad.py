import os

from .config import settings


def activar_langsmith() -> None:
    # pydantic-settings lee el .env pero no lo exporta: LangSmith lee os.environ
    if settings.langsmith_api_key:
        os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)
        os.environ.setdefault("LANGSMITH_TRACING", "true")
        os.environ.setdefault("LANGSMITH_PROJECT", "AURA-MultiAgentes-IA")
