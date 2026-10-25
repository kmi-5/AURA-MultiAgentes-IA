import uuid
from datetime import date

import pytest
from langgraph.types import Command
from sqlalchemy import delete, func, select

from backend.app.core.checkpointer import get_checkpointer, make_thread_id
from backend.app.core.db import SessionLocal
from backend.app.data.casos_prueba import CASOS, entrada_de
from backend.app.graph.ensamblado import armar_grafo
from backend.app.models.db_models import (
    AlertaSeguridad, Auditoria, Paciente, PaseTurno, UsuarioEnfermeria,
)

CASO = CASOS[2]                      # saturación baja y taquipnea; el paciente de prueba tiene 67 años


@pytest.fixture
def ids():
    sufijo = uuid.uuid4().hex[:8]
    with SessionLocal.begin() as s:
        paciente = Paciente(nombre=f"Integración {sufijo} (Prueba)", edad=67, habitacion="999")
        usuario = UsuarioEnfermeria(nombre="Test", username=f"test_{sufijo}", rol="enfermeria",
                                    password_hash="x")
        s.add_all([paciente, usuario])
        s.flush()
        ids = (paciente.id, usuario.id)
    yield ids
    with SessionLocal.begin() as s:                      # el paciente arrastra sus filas (CASCADE)
        s.execute(delete(Auditoria).where(Auditoria.usuario_id == ids[1]))
        s.execute(delete(Paciente).where(Paciente.id == ids[0]))
        s.execute(delete(UsuarioEnfermeria).where(UsuarioEnfermeria.id == ids[1]))


def _config(paciente_id):
    return {"configurable": {"thread_id": make_thread_id(paciente_id, "manana", date.today())}}


def _inicio(paciente_id, usuario_id, clave):
    return {"paciente_id": paciente_id, "turno": "manana", "usuario_id": usuario_id,
            "idempotency_key": clave, "entrada_cruda": entrada_de(CASO, paciente_id)}


def _contar_pases(paciente_id):
    with SessionLocal() as s:
        return s.scalar(select(func.count()).select_from(PaseTurno)
                        .where(PaseTurno.paciente_id == paciente_id))


def _grafo():
    checkpointer = get_checkpointer()
    checkpointer.setup()             # idempotente. El pool NO se cierra: está cacheado y lo usan otros tests
    return armar_grafo(checkpointer=checkpointer)


def test_un_turno_completo_contra_postgres(ids):
    paciente_id, usuario_id = ids
    config, grafo = _config(paciente_id), _grafo()

    grafo.invoke(_inicio(paciente_id, usuario_id, uuid.uuid4().hex), config)
    assert grafo.get_state(config).next == ("aprobacion",)
    grafo.invoke(Command(resume={"decision": "aprobado"}), config)
    assert grafo.get_state(config).next == ()

    with SessionLocal() as s:
        tipos = {a.tipo_alerta for a in s.scalars(
            select(AlertaSeguridad).where(AlertaSeguridad.paciente_id == paciente_id))}
    assert tipos == CASO["alertas_esperadas"]
    assert _contar_pases(paciente_id) == 1


def test_el_doble_click_no_duplica_registros_en_postgres(ids):
    paciente_id, usuario_id = ids
    config, grafo, clave = _config(paciente_id), _grafo(), uuid.uuid4().hex

    for _ in range(2):
        grafo.invoke(_inicio(paciente_id, usuario_id, clave), config)
        grafo.invoke(Command(resume={"decision": "aprobado"}), config)

    assert _contar_pases(paciente_id) == 1
