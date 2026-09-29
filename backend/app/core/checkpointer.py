from functools import lru_cache
from datetime import date
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver

from .config import settings


def make_thread_id(paciente_id: int, turno: str, fecha: date) -> str:
    """Un thread (= un checkpoint aislado) por paciente-turno-día."""
    return f"{paciente_id}:{turno}:{fecha.isoformat()}"


@lru_cache(maxsize=1)
def get_pool() -> ConnectionPool:
    pool = ConnectionPool(
        conninfo=settings.database_url,           # URL "postgresql://", NO la de SQLAlchemy
        min_size=1,
        max_size=10,
        # Requeridos por PostgresSaver: autocommit, sin prepared statements, filas como dict
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        check=ConnectionPool.check_connection,    # Neon suspende conexiones inactivas
        open=False,
    )
    pool.open(wait=True, timeout=30)              # 30 s por si Neon está "despertando"
    return pool


def get_checkpointer() -> PostgresSaver:
    return PostgresSaver(get_pool())


if __name__ == "__main__":
    get_checkpointer().setup()   # crea las tablas checkpoint* (idempotente)
    get_pool().close()
    print("Checkpointer listo")
