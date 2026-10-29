"""Configuración del frontend. Solo variables de entorno; nada de secretos en el repo."""
import os


def api_url() -> str:
    return os.getenv("API_URL", "http://localhost:8000").rstrip("/")


def timeout_s() -> float:
    return float(os.getenv("API_TIMEOUT_S", "120"))


def es_dev() -> bool:
    return os.getenv("AURA_ENTORNO", "prod").strip().lower() == "dev"
