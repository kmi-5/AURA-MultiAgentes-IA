from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from ..models.db_models import AlertaSeguridad, Auditoria, Paciente, PaseTurno, Tarea
from .deps import get_db, requiere_rol
from .esquemas import AlertaGuardadaOut, AuditoriaOut, PacienteOut, PaseOut, TareaOut

router = APIRouter(tags=["consultas"])
TODOS = ("enfermeria", "supervision", "auditoria")
OPERA = ("enfermeria", "supervision")
CONTROL = ("supervision", "auditoria")


def _paciente_o_404(db, paciente_id: int) -> None:
    if db.get(Paciente, paciente_id) is None:
        raise HTTPException(404, "Paciente inexistente")


@router.get("/pacientes", response_model=list[PacienteOut],
            dependencies=[Depends(requiere_rol(*TODOS))])
def listar_pacientes(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                     db=Depends(get_db)):
    return db.scalars(select(Paciente).order_by(Paciente.id).limit(limit).offset(offset)).all()


@router.get("/pacientes/{paciente_id}/pase", response_model=PaseOut,
            dependencies=[Depends(requiere_rol(*TODOS))])
def ultimo_pase(paciente_id: int, turno: Literal["manana", "tarde", "noche"] | None = None,
                db=Depends(get_db)):
    _paciente_o_404(db, paciente_id)
    q = select(PaseTurno).where(PaseTurno.paciente_id == paciente_id)
    if turno:
        q = q.where(PaseTurno.turno == turno)
    pase = db.scalars(q.order_by(PaseTurno.timestamp_generacion.desc(), PaseTurno.id.desc()).limit(1)).first()
    if pase is None:
        raise HTTPException(404, "Sin pase de guardia para ese paciente")
    return pase


@router.get("/pacientes/{paciente_id}/tareas", response_model=list[TareaOut],
            dependencies=[Depends(requiere_rol(*OPERA))])
def tareas_del_paciente(paciente_id: int, estado: Literal["pendiente", "completada"] | None = None,
                        db=Depends(get_db)):
    _paciente_o_404(db, paciente_id)
    q = select(Tarea).where(Tarea.paciente_id == paciente_id)
    if estado:
        q = q.where(Tarea.estado == estado)
    return db.scalars(q.order_by(Tarea.horario, Tarea.id)).all()


@router.get("/pacientes/{paciente_id}/alertas", response_model=list[AlertaGuardadaOut],
            dependencies=[Depends(requiere_rol(*TODOS))])
def alertas_del_paciente(paciente_id: int, db=Depends(get_db)):
    _paciente_o_404(db, paciente_id)
    return db.scalars(select(AlertaSeguridad).where(AlertaSeguridad.paciente_id == paciente_id)
                      .order_by(AlertaSeguridad.timestamp.desc(), AlertaSeguridad.id.desc())).all()


@router.get("/auditoria", response_model=list[AuditoriaOut],
            dependencies=[Depends(requiere_rol(*CONTROL))])
def consultar_auditoria(usuario_id: int | None = None, tarea: str | None = Query(None, max_length=80),
                        limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                        db=Depends(get_db)):
    q = select(Auditoria)
    if usuario_id is not None:
        q = q.where(Auditoria.usuario_id == usuario_id)
    if tarea:
        q = q.where(Auditoria.tarea == tarea)
    return db.scalars(q.order_by(Auditoria.id.desc()).limit(limit).offset(offset)).all()
