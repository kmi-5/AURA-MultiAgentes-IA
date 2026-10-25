"""Nodo de aprobación humana (paso 2.5): la enfermera valida antes de guardar."""
from typing import Literal

from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..agents.documentacion import MAX_EVOLUCION
from ..core.sanitizar import normalizar_texto
from .nodos import documentacion_ok, seguridad_ok


class DecisionHumana(BaseModel):
    """Lo que debe enviar la interfaz para reanudar el grafo."""
    model_config = ConfigDict(extra="forbid")

    decision: Literal["aprobado", "editado", "descartado"]
    evolucion_editada: str | None = Field(default=None, max_length=MAX_EVOLUCION)

    @field_validator("evolucion_editada")
    @classmethod
    def _normalizar(cls, v: str | None) -> str | None:
        return None if v is None else normalizar_texto(v)

    @model_validator(mode="after")
    def _coherente(self):
        if self.decision == "editado" and not self.evolucion_editada:
            raise ValueError("La decisión 'editado' requiere evolucion_editada")
        if self.decision != "editado" and self.evolucion_editada is not None:
            raise ValueError("Solo la decisión 'editado' lleva evolucion_editada")
        return self


def vista_para_revision(state: dict) -> dict:
    """Lo que ve la enfermera. No muestra datos de una rama que falló (podrían ser de otra ejecución)."""
    seg = seguridad_ok(state)
    return {
        "evolucion": state.get("evolucion") if documentacion_ok(state) else None,
        "seguridad_disponible": seg,
        "alertas": [a.model_dump() for a in state.get("alertas_actuales", [])] if seg else [],
        "puntajes_escalas": state.get("puntajes_escalas", {}) if seg else {},
        "avisos_seguridad": state.get("avisos_seguridad", []) if seg else [],
        "requiere_revision": state.get("requiere_revision", False),
        "turno_incompleto": state.get("turno_incompleto", False),
    }


def nodo_aprobacion(state: dict) -> dict:
    # Al reanudar, LangGraph vuelve a ejecutar este nodo desde el principio:
    # por eso no hay efectos secundarios antes de interrupt().
    respuesta = interrupt(vista_para_revision(state))
    decision = DecisionHumana.model_validate(respuesta)

    salida: dict = {"decision_humana": decision.decision, "estado_nodos": {"aprobacion": "ok"}}
    if decision.decision == "editado":
        salida["evolucion"] = decision.evolucion_editada
    return salida
