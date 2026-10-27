from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.db import Base
from backend.app.core.idempotencia import completar, huella_payload, liberar, reclamar
from backend.app.models.db_models import Idempotencia

U, EP, K = 1, "procesar", "clave-unit-0001"


@pytest.fixture
def sf():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


def _reclamar(sf, huella="h1", clave=K):
    with sf() as db:                      # una sesión por llamada, como en cada request real
        return reclamar(db, U, EP, clave, huella)[0]


def test_primera_vez_es_nuevo(sf):
    assert _reclamar(sf) == "nuevo"


def test_repetido_devuelve_la_respuesta_guardada(sf):
    _reclamar(sf)
    with sf() as db:
        completar(db, U, EP, K, 200, {"ok": True})
    with sf() as db:
        res, reg = reclamar(db, U, EP, K, "h1")
    assert res == "repetido" and reg.respuesta == {"ok": True} and reg.status_code == 200


def test_sin_completar_figura_en_proceso(sf):
    _reclamar(sf)
    assert _reclamar(sf) == "en_proceso"


def test_misma_clave_otra_huella_es_conflicto(sf):
    _reclamar(sf, "h1")
    assert _reclamar(sf, "h2") == "conflicto"


def test_claves_distintas_no_se_pisan(sf):
    assert _reclamar(sf, clave="clave-unit-0001") == "nuevo"
    assert _reclamar(sf, clave="clave-unit-0002") == "nuevo"


def test_registro_vencido_se_reemplaza(sf):
    _reclamar(sf)
    with sf() as db:
        reg = db.get(Idempotencia, (U, EP, K))
        reg.expira_en = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
    assert _reclamar(sf) == "nuevo"


def test_liberar_permite_reintentar(sf):
    _reclamar(sf)
    with sf() as db:
        liberar(db, U, EP, K)
    assert _reclamar(sf) == "nuevo"


def test_liberar_no_borra_lo_ya_completado(sf):
    _reclamar(sf)
    with sf() as db:
        completar(db, U, EP, K, 200, {"ok": True})
    with sf() as db:
        liberar(db, U, EP, K)
    assert _reclamar(sf) == "repetido"


def test_huella_no_depende_del_orden_de_las_claves():
    assert huella_payload({"a": 1, "b": [1, 2]}) == huella_payload({"b": [1, 2], "a": 1})
    assert huella_payload({"a": 1}) != huella_payload({"a": 2})
