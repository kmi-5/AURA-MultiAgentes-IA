"""Nodo Enfermería del grafo (paso 2.4).

Determinista, sin LLM: el payload ya llega estructurado y validado. Este nodo arma
DatosEstructurados (la edad sale de la tabla pacientes) y la lista de tareas del turno.
No diagnostica ni interpreta. Los dueños únicos de su salida son datos_estructurados y tareas.
"""
import logging
from collections.abc import Callable

from pydantic import ValidationError

from ..models.schemas import DatosEntrada, DatosEstructurados
from ..models.state import TurnoState
from .seguridad import edad_desde_db

logger = logging.getLogger(__name__)

# PROVISORIO (convención local, validar con la colega clínica): sirven para ordenar las
# tareas dentro del turno y para ubicar el control de signos vitales.
INICIO_TURNO = {"manana": "06:00", "tarde": "14:00", "noche": "22:00"}
HORARIO_CONTROL = {"manana": "10:00", "tarde": "18:00", "noche": "02:00"}


def _minutos(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _desplazamiento(hhmm: str, turno: str) -> int:
    """Minutos desde el inicio del turno (resuelve el cruce de medianoche del turno noche)."""
    return (_minutos(hhmm) - _minutos(INICIO_TURNO[turno])) % 1440


def armar_tareas(entrada: DatosEntrada) -> list[dict]:
    tareas = [
        {"tipo": "medicacion", "horario": h, "estado": "pendiente",
         "descripcion": "Medicación programada"}
        for h in entrada.medicacion_programada
    ]
    tareas.append({"tipo": "control", "horario": HORARIO_CONTROL[entrada.turno],
                   "estado": "pendiente", "descripcion": "Control de signos vitales"})
    return sorted(tareas, key=lambda t: _desplazamiento(t["horario"], entrada.turno))


def crear_nodo_enfermeria(obtener_edad: Callable[[int], int | None] = edad_desde_db):
    def nodo_enfermeria(state: TurnoState) -> dict:
        try:
            entrada = DatosEntrada.model_validate(state.get("entrada_cruda", {}))
        except ValidationError as e:
            # se vuelve a validar aunque FastAPI ya lo hizo: el grafo no confía en su entrada
            logger.warning("Entrada inválida en Enfermería (%d errores)", e.error_count())
            return {"errores": ["enfermeria: entrada inválida"],
                    "estado_nodos": {"enfermeria": "error"}}

        edad = obtener_edad(entrada.paciente_id)
        if edad is None:
            return {"errores": [f"enfermeria: paciente {entrada.paciente_id} no encontrado"],
                    "estado_nodos": {"enfermeria": "error"}}

        datos = DatosEstructurados(
            paciente_id=entrada.paciente_id,
            turno=entrada.turno,
            edad=edad,
            signos_vitales=entrada.signos_vitales,
            observacion=entrada.observacion,
            dispositivos=entrada.dispositivos,
            medicacion_programada=entrada.medicacion_programada,
            valoracion_caidas=entrada.valoracion_caidas,
        )
        return {
            "datos_estructurados": datos,
            "tareas": armar_tareas(entrada),
            "estado_nodos": {"enfermeria": "ok"},
        }

    return nodo_enfermeria
