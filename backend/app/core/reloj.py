"""Hora local de Buenos Aires. Inyectable en los nodos para poder probarlos."""
from datetime import datetime
from zoneinfo import ZoneInfo

ZONA = ZoneInfo("America/Argentina/Buenos_Aires")


def ahora_ba() -> datetime:
    return datetime.now(ZONA)
