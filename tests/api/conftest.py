import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.db import Base
from backend.app.core.seguridad import hashear_password
from backend.app.graph.ensamblado import armar_grafo
from backend.app.main import crear_app
from backend.app.models.db_models import Paciente, UsuarioEnfermeria
from backend.app.routers import auth

PASSWORDS = {"enfermeria": "clave-enfermera-1",
             "supervision": "clave-supervisora-1",
             "auditoria": "clave-auditor-1"}
_HASHES = {rol: hashear_password(p) for rol, p in PASSWORDS.items()}   # argon2 es lento: se calcula una vez


class GrafoEspia:
    """Envuelve el grafo real y cuenta cuántas veces se lo invoca."""
    def __init__(self, g):
        self._g, self.invocaciones = g, 0

    def invoke(self, *a, **k):
        self.invocaciones += 1
        return self._g.invoke(*a, **k)

    def __getattr__(self, nombre):
        return getattr(self._g, nombre)


@pytest.fixture
def session_factory():
    # StaticPool + check_same_thread=False: los endpoints `def` corren en threads distintos
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    f = sessionmaker(engine, expire_on_commit=False)
    with f.begin() as s:
        for rol, h in _HASHES.items():
            s.add(UsuarioEnfermeria(nombre=f"Test {rol}", username=f"{rol}.test", rol=rol, password_hash=h))
        for i in range(1, 6):
            s.add(Paciente(nombre=f"Paciente {i}", edad=60, habitacion=str(100 + i)))
    yield f
    engine.dispose()


@pytest.fixture
def grafo_de(session_factory):
    """Fábrica de grafos de prueba: sin Gemini, sin Neon (obtener_edad inyectada a mano)."""
    def _crear(fabrica=None):
        return GrafoEspia(armar_grafo(
            checkpointer=MemorySaver(),
            session_factory=fabrica or session_factory,
            obtener_edad=lambda _paciente_id: 80,      # el default leería de Neon
            redactor_alertas=None, redactor_evolucion=None))
    return _crear


@pytest.fixture
def grafo(grafo_de):
    return grafo_de()


@pytest.fixture
def make_client(session_factory):
    auth.limiter.enabled = False
    def _crear(g):
        return TestClient(crear_app(session_factory=session_factory, grafo=g))   # sin 'with': sin lifespan
    return _crear


@pytest.fixture
def client(make_client, grafo):
    return make_client(grafo)


@pytest.fixture
def passwords():
    return PASSWORDS


@pytest.fixture
def auth_headers(client):
    def _h(rol: str = "enfermeria", clave: str = "clave-de-prueba-001", cliente=None) -> dict:
        c = cliente or client
        r = c.post("/auth/login", json={"username": f"{rol}.test", "password": PASSWORDS[rol]})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}", "Idempotency-Key": clave}
    return _h