"""Nodo de persistencia (paso 2.6): guarda el turno aprobado, idempotente y atómico."""
import logging
from collections.abc import Callable
from datetime import datetime, time

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..core.db import SessionLocal
from ..core.reloj import ahora_ba
from ..models.db_models import (
    AlertaSeguridad, Auditoria, PaseTurno, SignosVitalesRow, Tarea, ValoracionCaidasRow,
)
from .nodos import seguridad_ok

logger = logging.getLogger(__name__)


def _existe(session, clave: str) -> bool:
    return session.scalar(select(PaseTurno.id).where(PaseTurno.idempotency_key == clave)) is not None


def _guardar(s, state: dict, momento: datetime) -> None:
    datos = state["datos_estructurados"]
    paciente_id = state["paciente_id"]
    turno = state["turno"]
    usuario_id = state["usuario_id"]
    incompleto = bool(state.get("turno_incompleto"))

    # El pase va primero: su clave única corta un reenvío antes de escribir el resto.
    s.add(PaseTurno(paciente_id=paciente_id, turno=turno,
                    contenido_consolidado=state.get("pase_guardia", ""),
                    idempotency_key=state["idempotency_key"], incompleto=incompleto))
    s.flush()

    s.add(SignosVitalesRow(paciente_id=paciente_id, **datos.signos_vitales.model_dump(mode="json")))
    if datos.valoracion_caidas is not None:
        s.add(ValoracionCaidasRow(paciente_id=paciente_id, turno=turno,
                                  **datos.valoracion_caidas.model_dump(mode="json")))

    # Si Seguridad falló, alertas_actuales puede venir de otra ejecución: no se guarda.
    if seguridad_ok(state):
        for a in state.get("alertas_actuales", []):
            s.add(AlertaSeguridad(paciente_id=paciente_id, tipo_alerta=a.tipo_alerta,
                                  descripcion=a.descripcion, version_reglas=a.version_reglas))

    for t in state.get("tareas", []):
        s.add(Tarea(paciente_id=paciente_id, tipo=t["tipo"],
                    horario=time.fromisoformat(t["horario"]),
                    estado=t.get("estado", "pendiente"), responsable_id=usuario_id))
    if state.get("requiere_revision"):
        s.add(Tarea(paciente_id=paciente_id, tipo="revision",
                    horario=momento.time().replace(second=0, microsecond=0),
                    estado="pendiente", responsable_id=usuario_id))

    s.add(Auditoria(
        usuario_id=usuario_id,
        tarea="turno_editado" if state.get("decision_humana") == "editado" else "turno_aprobado",
        estado="incompleto" if incompleto else "ok",
    ))


def crear_nodo_persistencia(session_factory=SessionLocal,
                            ahora: Callable[[], datetime] = ahora_ba):
    def nodo_persistencia(state: dict) -> dict:
        if state.get("decision_humana") == "descartado":
            with session_factory.begin() as s:
                s.add(Auditoria(usuario_id=state["usuario_id"], tarea="turno_descartado",
                                estado="descartado"))
            return {"estado_nodos": {"persistencia": "ok"}}

        try:
            with session_factory.begin() as s:
                if _existe(s, state["idempotency_key"]):
                    return {"estado_nodos": {"persistencia": "ya_guardado"}}
                _guardar(s, state, ahora())
        except IntegrityError:
            # dos ejecuciones con la misma clave a la vez: ganó la otra
            logger.warning("Guardado concurrente con la misma clave; ya estaba registrado")
            return {"estado_nodos": {"persistencia": "ya_guardado"}}
        return {"estado_nodos": {"persistencia": "ok"}}

    return nodo_persistencia
