import hashlib
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from langgraph.types import Command

from ..core.auditoria import TareaAuditoria, registrar
from ..core.checkpointer import make_thread_id
from ..core.idempotencia import completar, huella_payload, liberar, reclamar
from ..core.reloj import ahora_ba
from ..graph.aprobacion import vista_para_revision
from ..models.db_models import Paciente
from ..models.schemas import DatosEntrada
from .deps import UsuarioActual, get_db, get_grafo, requiere_rol
from .esquemas import DecisionIn, TurnoOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/turnos", tags=["turnos"])

ROLES_OPERA = ("enfermeria", "supervision")
ETAPAS_PENDIENTES = {"aprobacion", "consolidar", "persistencia"}


def _clave_estado(usuario_id: int, thread_id: str, clave_http: str) -> str:
    """64 caracteres hex: cabe justo en pases_turno.idempotency_key (String(64))."""
    return hashlib.sha256(f"{usuario_id}:{thread_id}:{clave_http}".encode()).hexdigest()


def _config(thread_id: str, usuario: UsuarioActual, rid: str | None) -> dict:
    return {"configurable": {"thread_id": thread_id},
            "metadata": {"usuario_id": usuario.id, "request_id": rid}}


def _plano(x):
    return x.model_dump(mode="json") if hasattr(x, "model_dump") else x


def _a_turno(snap, thread_id: str) -> TurnoOut:
    vals = snap.values or {}
    interrupts = [i for t in snap.tasks for i in t.interrupts]
    if interrupts:
        estado, revision = "pendiente_aprobacion", interrupts[0].value
    else:
        revision = vista_para_revision(vals)
        if snap.next:
            estado = "persistencia_pendiente"
        elif vals.get("decision_humana") == "descartado":
            estado = "descartado"
        else:
            estado = "completado"
    revision = {**revision, "alertas": [_plano(a) for a in revision.get("alertas", [])]}
    return TurnoOut(thread_id=thread_id, estado=estado, revision=revision,
                    estado_nodos=vals.get("estado_nodos", {}),
                    tareas=[_plano(t) for t in vals.get("tareas", [])],
                    procesado_por=vals.get("usuario_id"))


def _respuesta_previa(res: str, reg):
    """Traduce el resultado de reclamar() cuando NO hay que ejecutar nada."""
    if res == "repetido":
        return JSONResponse(reg.respuesta, status_code=reg.status_code,
                            headers={"Idempotent-Replay": "true"})
    if res == "en_proceso":
        raise HTTPException(409, "Ya hay una solicitud en curso con esta clave")
    if res == "conflicto":
        raise HTTPException(422, "La clave de idempotencia ya se usó con otro contenido")
    return None


@router.post("/procesar", response_model=TurnoOut)
def procesar_turno(
    payload: DatosEntrada, request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    usuario: UsuarioActual = Depends(requiere_rol(*ROLES_OPERA)),
    db=Depends(get_db), grafo=Depends(get_grafo),
):
    rid = getattr(request.state, "request_id", None)
    res, reg = reclamar(db, usuario.id, "procesar", idempotency_key,
                        huella_payload(payload.model_dump(mode="json")))
    if (previa := _respuesta_previa(res, reg)) is not None:
        return previa

    thread_id = make_thread_id(payload.paciente_id, payload.turno, ahora_ba().date())
    config = _config(thread_id, usuario, rid)
    try:
        if db.get(Paciente, payload.paciente_id) is None:
            liberar(db, usuario.id, "procesar", idempotency_key)
            raise HTTPException(404, "Paciente inexistente")
        if ETAPAS_PENDIENTES & set(grafo.get_state(config).next):
            liberar(db, usuario.id, "procesar", idempotency_key)
            raise HTTPException(409, "Este paciente-turno tiene un procesamiento pendiente de resolver")
        grafo.invoke({"thread_id": thread_id,
                      "paciente_id": payload.paciente_id,
                      "turno": payload.turno,
                      "usuario_id": usuario.id,
                      "idempotency_key": _clave_estado(usuario.id, thread_id, idempotency_key),
                      "entrada_cruda": payload.model_dump(mode="json")},
                     config)
        turno = _a_turno(grafo.get_state(config), thread_id)
    except HTTPException:
        raise
    except Exception as e:
        # solo el tipo: el mensaje o el traceback podrían incluir datos del paciente
        logger.error("Fallo procesando turno rid=%s tipo=%s", rid, type(e).__name__)
        liberar(db, usuario.id, "procesar", idempotency_key)
        registrar(db, usuario_id=usuario.id, tarea=TareaAuditoria.PROCESAR, estado="error",
                  detalle={"error": type(e).__name__}, request_id=rid)
        raise HTTPException(502, "No se pudo procesar el turno")

    cuerpo = turno.model_dump(mode="json")
    completar(db, usuario.id, "procesar", idempotency_key, 200, cuerpo)
    registrar(db, usuario_id=usuario.id, tarea=TareaAuditoria.PROCESAR, estado="ok",
              detalle={"thread_id": thread_id}, request_id=rid)
    return cuerpo


@router.post("/{thread_id}/decision", response_model=TurnoOut)
def decidir_turno(
    thread_id: str, body: DecisionIn, request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    usuario: UsuarioActual = Depends(requiere_rol(*ROLES_OPERA)),
    db=Depends(get_db), grafo=Depends(get_grafo),
):
    rid = getattr(request.state, "request_id", None)
    res, reg = reclamar(db, usuario.id, "decision", idempotency_key,
                        huella_payload({"thread_id": thread_id, **body.model_dump(mode="json")}))
    if (previa := _respuesta_previa(res, reg)) is not None:
        return previa

    config = _config(thread_id, usuario, rid)
    try:
        snap = grafo.get_state(config)
        if not snap.values:
            liberar(db, usuario.id, "decision", idempotency_key)
            raise HTTPException(404, "Turno inexistente")
        if any(t.interrupts for t in snap.tasks):
            grafo.invoke(Command(resume=body.model_dump(exclude={"motivo"})), config)
        elif snap.next:                   # el guardado falló antes: se reanuda
            if body.decision != snap.values.get("decision_humana"):
                liberar(db, usuario.id, "decision", idempotency_key)
                raise HTTPException(409, "El turno ya tiene una decisión distinta registrada")
            grafo.invoke(None, config)
        else:
            liberar(db, usuario.id, "decision", idempotency_key)
            raise HTTPException(409, "El turno no tiene una decisión pendiente")
        turno = _a_turno(grafo.get_state(config), thread_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Fallo aplicando decisión rid=%s tipo=%s", rid, type(e).__name__)
        liberar(db, usuario.id, "decision", idempotency_key)
        registrar(db, usuario_id=usuario.id, tarea=TareaAuditoria.DECISION, estado="error",
                  detalle={"thread_id": thread_id, "error": type(e).__name__}, request_id=rid)
        raise HTTPException(503, "No se pudo guardar el turno; reintentá la decisión")

    cuerpo = turno.model_dump(mode="json")
    completar(db, usuario.id, "decision", idempotency_key, 200, cuerpo)
    registrar(db, usuario_id=usuario.id, tarea=TareaAuditoria.DECISION, estado="ok",
              detalle={"thread_id": thread_id, "decision": body.decision,
                       "motivo": body.motivo, "procesado_por": turno.procesado_por},
              request_id=rid)
    return cuerpo


@router.get("/{thread_id}", response_model=TurnoOut)
def consultar_turno(thread_id: str, request: Request,
                    usuario: UsuarioActual = Depends(requiere_rol(*ROLES_OPERA)),
                    grafo=Depends(get_grafo)):
    snap = grafo.get_state(_config(thread_id, usuario, getattr(request.state, "request_id", None)))
    if not snap.values:
        raise HTTPException(404, "Turno inexistente")
    return _a_turno(snap, thread_id)