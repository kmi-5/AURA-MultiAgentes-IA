import pytest
from sqlalchemy import func, select
from backend.app.core.db import SessionLocal
from backend.app.core.seed import run
from backend.app.data.casos_prueba import CASOS
from backend.app.models.db_models import (
    Medicacion,
    Paciente,
    SignosVitalesRow,
    Tarea,
    ValoracionCaidasRow,
)

@pytest.fixture(autouse=True, scope="module")
def base_con_el_seed_limpio():
    run(reset=True)          # el módulo parte siempre del seed, sin restos del demo

def _conteos():
    with SessionLocal() as s:
        return {
            m.__tablename__: s.scalar(select(func.count()).select_from(m))
            for m in (Paciente, SignosVitalesRow, ValoracionCaidasRow, Medicacion, Tarea)
        }


def test_el_seed_cargo_los_10_casos():
    with SessionLocal() as s:
        nombres = set(s.scalars(select(Paciente.nombre)))

    assert {c["nombre"] for c in CASOS} <= nombres


def test_el_seed_guarda_los_datos_de_news2_y_morse():
    with SessionLocal() as s:
        for c in CASOS:
            p = s.scalar(select(Paciente).where(Paciente.nombre == c["nombre"]))
            sv = s.scalar(select(SignosVitalesRow).where(SignosVitalesRow.paciente_id == p.id))
            assert sv.o2_suplementario == c["signos"]["o2_suplementario"]
            assert sv.conciencia == c["signos"]["conciencia"]

            v = s.scalar(select(ValoracionCaidasRow).where(ValoracionCaidasRow.paciente_id == p.id))
            for campo, valor in c["caidas"].items():
                assert getattr(v, campo) == valor, (c["escenario"], campo)


def test_el_seed_no_duplica_tareas():
    # una tarea por medicación + un control por paciente
    esperadas = sum(len(c["medicacion"]) for c in CASOS) + len(CASOS)
    assert _conteos()["tareas"] == esperadas


def test_el_seed_es_idempotente():
    antes = _conteos()
    run()
    assert _conteos() == antes