"""Ensamblado de producción: nodos reales con dependencias inyectables (paso 2.8)."""
from collections.abc import Callable
from datetime import datetime

from ..agents.documentacion import crear_nodo_documentacion
from ..agents.enfermeria import crear_nodo_enfermeria
from ..agents.seguridad import crear_nodo_seguridad, edad_desde_db
from ..core.db import SessionLocal
from ..core.reloj import ahora_ba
from .builder import construir_grafo
from .consolidar import crear_nodo_consolidar
from .persistencia import crear_nodo_persistencia


def armar_grafo(
    *,
    checkpointer,
    obtener_edad: Callable[[int], int | None] = edad_desde_db,
    session_factory=SessionLocal,
    redactor_alertas=None,
    redactor_evolucion=None,
    timeout_s: float = 60.0,
    ahora: Callable[[], datetime] = ahora_ba,
):
    return construir_grafo(
        enfermeria=crear_nodo_enfermeria(obtener_edad=obtener_edad),
        seguridad=crear_nodo_seguridad(obtener_edad=obtener_edad, redactor=redactor_alertas),
        documentacion=crear_nodo_documentacion(redactor=redactor_evolucion),
        consolidar=crear_nodo_consolidar(ahora=ahora),
        persistencia=crear_nodo_persistencia(session_factory=session_factory, ahora=ahora),
        checkpointer=checkpointer,
        timeout_s=timeout_s,
    )
