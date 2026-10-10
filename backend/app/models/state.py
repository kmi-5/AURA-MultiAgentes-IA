import operator
from typing import Annotated, Literal, TypedDict

from .schemas import Alerta, DatosEstructurados


def merge_dicts(actual: dict, nuevo: dict) -> dict:
    """Reducer: fusiona diccionarios sin pisar claves de la otra rama."""
    return {**(actual or {}), **(nuevo or {})}


def merge_alertas(actual: list[Alerta], nuevas: list[Alerta]) -> list[Alerta]:
    """Reducer: acumula alertas y descarta duplicados (reintentos, re-ejecuciones)."""
    vistas = {(a.tipo_alerta, a.version_reglas) for a in (actual or [])}
    resultado = list(actual or [])
    for a in (nuevas or []):
        clave = (a.tipo_alerta, a.version_reglas)
        if clave not in vistas:
            vistas.add(clave)
            resultado.append(a)
    return resultado


class TurnoState(TypedDict, total=False):
    # --- Identidad e idempotencia (las setea FastAPI antes de invocar el grafo) ---
    thread_id: str                  # "{paciente_id}:{turno}:{fecha}" -> ver make_thread_id()
    paciente_id: int
    turno: Literal["manana", "tarde", "noche"]
    usuario_id: int
    idempotency_key: str

    # --- Entrada ---
    entrada_cruda: dict

    # --- Dueño único: Agente Enfermería ---
    datos_estructurados: DatosEstructurados
    tareas: list[dict]

    # --- Dueño único: Agente Documentación ---
    evolucion: str

    # --- Dueño único: Agente Seguridad (acumula con deduplicación) ---
    alertas: Annotated[list[Alerta], merge_alertas]
     
    puntajes_escalas: dict[str, int]    # {"news2": 6, "morse": 45}; lo escribe solo Seguridad

    avisos_seguridad: list[str]         # news2_parcial / news2_no_aplicable / morse_no_evaluable; solo Seguridad

    # --- Escriben AMBAS ramas paralelas: reducers obligatorios ---
    errores: Annotated[list[str], operator.add]
    estado_nodos: Annotated[dict[str, str], merge_dicts]

    # --- Dueño único: nodo Join ---
    requiere_revision: bool
    turno_incompleto: bool

    # --- Dueño único: nodo de aprobación humana ---
    decision_humana: Literal["aprobado", "editado", "descartado"]

    # --- Memoria del turno: acumula entre invocaciones del mismo thread ---
    historial_turno: Annotated[list[dict], operator.add]
    pase_guardia: str