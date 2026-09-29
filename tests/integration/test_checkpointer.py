import uuid
from datetime import date

from langgraph.graph import StateGraph, START, END

from backend.app.core.checkpointer import get_checkpointer, make_thread_id
from backend.app.models.state import TurnoState


def _grafo_minimo():
    def registrar(state):
        return {"historial_turno": [{"evento": "procesado"}]}

    g = StateGraph(TurnoState)
    g.add_node("registrar", registrar)
    g.add_edge(START, "registrar")
    g.add_edge("registrar", END)
    return g.compile(checkpointer=get_checkpointer())


def test_el_estado_persiste_y_se_acumula_entre_invocaciones():
    grafo = _grafo_minimo()
    # paciente_id aleatorio para no chocar con datos reales; hoy + uuid = thread único
    tid = make_thread_id(paciente_id=900000 + uuid.uuid4().int % 99999, turno="manana", fecha=date.today())
    cfg = {"configurable": {"thread_id": tid}}
    try:
        r1 = grafo.invoke({"paciente_id": 1}, cfg)
        assert len(r1["historial_turno"]) == 1

        r2 = grafo.invoke({"paciente_id": 1}, cfg)          # 2° input del MISMO turno
        assert len(r2["historial_turno"]) == 2               # acumuló, no reemplazó

        # El estado sobrevive: se lee desde Postgres, no desde memoria de Python
        assert len(grafo.get_state(cfg).values["historial_turno"]) == 2
    finally:
        get_checkpointer().delete_thread(tid)


def test_threads_distintos_estan_aislados():
    grafo = _grafo_minimo()
    base = 900000 + uuid.uuid4().int % 99999
    tid_a = make_thread_id(base, "manana", date.today())
    tid_b = make_thread_id(base + 1, "manana", date.today())
    try:
        grafo.invoke({"paciente_id": 1}, {"configurable": {"thread_id": tid_a}})
        grafo.invoke({"paciente_id": 1}, {"configurable": {"thread_id": tid_a}})
        rb = grafo.invoke({"paciente_id": 2}, {"configurable": {"thread_id": tid_b}})
        assert len(rb["historial_turno"]) == 1               # B no ve el historial de A
    finally:
        get_checkpointer().delete_thread(tid_a)
        get_checkpointer().delete_thread(tid_b)
