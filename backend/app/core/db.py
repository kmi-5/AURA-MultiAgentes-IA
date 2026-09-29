from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    """Base común de todos los modelos; Alembic lee su metadata."""


# pool_pre_ping: Neon suspende el compute por inactividad y las conexiones
# del pool pueden quedar cerradas. Esto las verifica antes de usarlas.
engine = create_engine(settings.sqlalchemy_url, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)
