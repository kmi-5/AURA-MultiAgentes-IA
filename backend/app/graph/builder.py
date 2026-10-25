"""Ensamblado del grafo de LangGraph (paso 2.5).

Los nodos llegan por parámetro: así se prueba el grafo con nodos reales o con stubs,
y el checkpointer (MemorySaver en tests, PostgresSaver en producción) se inyecta.
"""
from langgraph.graph import END, START, StateGraph

from ..models.state import TurnoState
from .aprobacion import nodo_aprobacion
from .nodos import (
    con_timeout, nodo_join, nodo_marcar_revision,
    ruta_post_aprobacion, ruta_post_enfermeria, ruta_post_join,
)


def construir_grafo(*, enfermeria, seguridad, documentacion, consolidar, persistencia,
                    checkpointer=None, timeout_s: float = 60.0):
    g = StateGraph(TurnoState)

    g.add_node("enfermeria", enfermeria)
    g.add_node("seguridad", con_timeout(seguridad, "seguridad", timeout_s))
    g.add_node("documentacion", con_timeout(documentacion, "documentacion", timeout_s))
    g.add_node("join", nodo_join)
    g.add_node("marcar_revision", nodo_marcar_revision)
    g.add_node("aprobacion", nodo_aprobacion)
    g.add_node("consolidar", consolidar)
    g.add_node("persistencia", persistencia)

    g.add_edge(START, "enfermeria")
    g.add_conditional_edges("enfermeria", ruta_post_enfermeria,
                            ["seguridad", "documentacion", END])
    g.add_edge(["seguridad", "documentacion"], "join")          # espera a las dos ramas
    g.add_conditional_edges("join", ruta_post_join, ["marcar_revision", "aprobacion"])
    g.add_edge("marcar_revision", "aprobacion")
    g.add_conditional_edges("aprobacion", ruta_post_aprobacion, ["consolidar", "persistencia"])
    g.add_edge("consolidar", "persistencia")
    g.add_edge("persistencia", END)

    return g.compile(checkpointer=checkpointer)
