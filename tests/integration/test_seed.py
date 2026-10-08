from sqlalchemy import func, select

from backend.app.core.db import SessionLocal
from backend.app.core.seed import run
from backend.app.data.casos_prueba import CASOS
from backend.app.models.db_models import (
    Paciente,
    SignosVitalesRow,
    Medicacion,
    Tarea,
)


def _conteos():
    with SessionLocal() as s:
        return {
            m.__tablename__: s.scalar(select(func.count()).select_from(m))
            for m in (Paciente, SignosVitalesRow, Medicacion, Tarea)
        }


def test_el_seed_cargo_los_10_casos():
    with SessionLocal() as s:
        nombres = set(s.scalars(select(Paciente.nombre)))

    assert {c["nombre"] for c in CASOS} <= nombres


def test_el_seed_es_idempotente():
    antes = _conteos()
    run()
    assert _conteos() == antes
