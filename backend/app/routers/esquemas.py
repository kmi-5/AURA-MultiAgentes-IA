from datetime import datetime, time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.sanitizar import normalizar_texto
from ..graph.aprobacion import DecisionHumana


class DecisionIn(DecisionHumana):
    """Cuerpo de POST /turnos/{thread_id}/decision.

    Hereda decision/evolucion_editada (y sus validadores) de DecisionHumana.
    'motivo' solo va a auditoría: nunca se pasa al grafo.
    """
    motivo: str | None = Field(default=None, max_length=300)

    @field_validator("motivo")
    @classmethod
    def _normalizar_motivo(cls, v: str | None) -> str | None:
        return None if v is None else (normalizar_texto(v) or None)


class AlertaOut(BaseModel):
    tipo_alerta: str
    descripcion: str
    version_reglas: str
    severidad: str

    @field_validator("severidad", mode="before")
    @classmethod
    def _valor_del_enum(cls, v):
        return getattr(v, "value", v)


class VistaRevision(BaseModel):
    evolucion: str | None
    seguridad_disponible: bool
    alertas: list[AlertaOut]
    puntajes_escalas: dict[str, int]
    avisos_seguridad: list[str]
    requiere_revision: bool
    turno_incompleto: bool


class TurnoOut(BaseModel):
    thread_id: str
    estado: Literal["pendiente_aprobacion", "completado", "descartado", "persistencia_pendiente"]
    revision: VistaRevision
    estado_nodos: dict[str, str]
    tareas: list[dict[str, Any]]
    procesado_por: int | None


class _Leible(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PacienteOut(_Leible):
    id: int
    nombre: str
    edad: int
    habitacion: str


class PaseOut(_Leible):
    id: int
    paciente_id: int
    turno: str
    contenido_consolidado: str
    incompleto: bool
    timestamp_generacion: datetime


class TareaOut(_Leible):
    id: int
    paciente_id: int
    tipo: str
    horario: time
    estado: str
    responsable_id: int | None


class AlertaGuardadaOut(_Leible):
    id: int
    paciente_id: int
    tipo_alerta: str
    descripcion: str
    estado_revision: str
    version_reglas: str
    timestamp: datetime


class AuditoriaOut(_Leible):
    id: int
    usuario_id: int | None
    tarea: str
    estado: str
    timestamp: datetime
    request_id: str | None
    detalle: dict | None