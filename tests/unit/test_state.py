from langgraph.graph import StateGraph, START, END
from backend.app.models.schemas import Alerta
from backend.app.models.state import TurnoState, merge_alertas, merge_dicts


def test_merge_dicts_no_pisa_claves():
    assert merge_dicts({"seguridad": "ok"}, {"documentacion": "timeout"}) == {
        "seguridad": "ok", "documentacion": "timeout"}


def test_merge_alertas_deduplica():
    a = Alerta(tipo_alerta="riesgo_caida", descripcion="x", version_reglas="v1")
    b = Alerta(tipo_alerta="riesgo_caida", descripcion="y", version_reglas="v1")
    c = Alerta(tipo_alerta="riesgo_caida", descripcion="z", version_reglas="v2")
    assert len(merge_alertas([a], [b, c])) == 2


def test_fanout_paralelo_combina_campos_compartidos():
    def enfermeria(state):
        return {"estado_nodos": {"enfermeria": "ok"}}

    def seguridad(state):
        return {
            "alertas": [Alerta(
                tipo_alerta="riesgo_caida",
                descripcion="d",
                version_reglas="v1"
            )],
            "estado_nodos": {"seguridad": "ok"},
            "errores": ["aviso de seguridad"],
        }

    def documentacion(state):
        return {
            "evolucion": "Paciente lúcido...",
            "estado_nodos": {"documentacion": "ok"},
            "errores": ["aviso de documentacion"],
        }

    def join(state):
        return {"requiere_revision": len(state.get("alertas", [])) > 0}

    g = StateGraph(TurnoState)
    g.add_node("enfermeria", enfermeria)
    g.add_node("seguridad", seguridad)
    g.add_node("documentacion", documentacion)
    g.add_node("join", join)

    g.add_edge(START, "enfermeria")
    g.add_edge("enfermeria", "seguridad")
    g.add_edge("enfermeria", "documentacion")
    g.add_edge(["seguridad", "documentacion"], "join")
    g.add_edge("join", END)

    resultado = g.compile().invoke({"paciente_id": 1})

    assert resultado["estado_nodos"] == {
        "enfermeria": "ok",
        "seguridad": "ok",
        "documentacion": "ok"
    }
    assert len(resultado["errores"]) == 2
    assert resultado["requiere_revision"] is True
    assert resultado["evolucion"].startswith("Paciente")
