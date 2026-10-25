import time
import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from backend.app.agents.documentacion import crear_nodo_documentacion
from backend.app.agents.enfermeria import crear_nodo_enfermeria
from backend.app.agents.seguridad import crear_nodo_seguridad
from backend.app.data.casos_limite import CASOS_LIMITE
from backend.app.data.casos_prueba import CASOS, entrada_de
from backend.app.graph.builder import construir_grafo
from backend.app.graph.nodos import con_timeout, nodo_join, ruta_post_join

TODOS = CASOS + CASOS_LIMITE
EDITADA = "Evolución corregida por la enfermera."


def _caso(escenario):
    return next(c for c in TODOS if c["escenario"] == escenario)


def _config(hilo="A"):
    return {"configurable": {"thread_id": f"1:manana:{hilo}"}}


def _roto(_state):
    raise RuntimeError("boom")


def _grafo(edad=60, *, enfermeria=None, seguridad=None, documentacion=None, timeout_s=5.0):
    llamadas = []

    def consolidar(_state):
        llamadas.append("consolidar")
        return {"estado_nodos": {"consolidar": "ok"}}

    def persistencia(state):
        llamadas.append(("persistencia", state.get("decision_humana")))
        return {"estado_nodos": {"persistencia": "ok"}}

    obtener_edad = lambda _pid: edad
    grafo = construir_grafo(
        enfermeria=enfermeria or crear_nodo_enfermeria(obtener_edad=obtener_edad),
        seguridad=seguridad or crear_nodo_seguridad(obtener_edad=obtener_edad),
        documentacion=documentacion or crear_nodo_documentacion(),
        consolidar=consolidar, persistencia=persistencia,
        checkpointer=MemorySaver(), timeout_s=timeout_s,
    )
    return grafo, llamadas


def _correr(grafo, caso, hilo="A"):
    entrada = {"paciente_id": 1, "turno": "manana", "usuario_id": 1,
               "idempotency_key": "k1", "entrada_cruda": entrada_de(caso, 1)}
    grafo.invoke(entrada, _config(hilo))
    return grafo.get_state(_config(hilo))


# --- flujo completo hasta la aprobación, con el golden set ---

@pytest.mark.parametrize("caso", TODOS, ids=lambda c: c["escenario"])
def test_el_grafo_llega_a_la_aprobacion_con_las_alertas_esperadas(caso):
    grafo, _ = _grafo(caso["edad"])
    estado = _correr(grafo, caso)
    v = estado.values

    assert estado.next == ("aprobacion",)
    assert {a.tipo_alerta for a in v["alertas_actuales"]} == caso["alertas_esperadas"]
    assert v["requiere_revision"] == bool(caso["alertas_esperadas"])
    assert v["turno_incompleto"] is False
    assert v["evolucion"]


# --- decisión humana ---

def test_aprobar_completa_el_flujo_y_persiste():
    grafo, llamadas = _grafo()
    _correr(grafo, CASOS[1])
    grafo.invoke(Command(resume={"decision": "aprobado"}), _config())

    estado = grafo.get_state(_config())
    assert estado.next == ()
    assert estado.values["decision_humana"] == "aprobado"
    assert llamadas == ["consolidar", ("persistencia", "aprobado")]


def test_editar_reemplaza_la_evolucion():
    grafo, llamadas = _grafo()
    _correr(grafo, CASOS[1])
    grafo.invoke(Command(resume={"decision": "editado", "evolucion_editada": EDITADA}), _config())

    v = grafo.get_state(_config()).values
    assert v["evolucion"] == EDITADA and v["decision_humana"] == "editado"
    assert llamadas == ["consolidar", ("persistencia", "editado")]


def test_descartar_no_consolida_pero_pasa_por_persistencia():
    grafo, llamadas = _grafo()
    _correr(grafo, CASOS[1])
    grafo.invoke(Command(resume={"decision": "descartado"}), _config())

    assert grafo.get_state(_config()).next == ()
    assert llamadas == [("persistencia", "descartado")]


@pytest.mark.parametrize("resume", [
    {"decision": "quizas"},
    {"decision": "editado"},
    {"decision": "aprobado", "evolucion_editada": "x"},
])
def test_una_decision_invalida_se_rechaza(resume):
    grafo, _ = _grafo()
    _correr(grafo, CASOS[1])
    with pytest.raises(ValueError):
        grafo.invoke(Command(resume=resume), _config())


# --- fallos parciales del fan-out ---

def test_si_seguridad_falla_el_turno_queda_incompleto_y_pide_revision():
    caso = CASOS[0]                                            # estable, sin alertas
    grafo, _ = _grafo(caso["edad"], seguridad=_roto)
    estado = _correr(grafo, caso)
    v = estado.values

    assert estado.next == ("aprobacion",)
    assert v["estado_nodos"]["seguridad"] == "error"
    assert v["turno_incompleto"] is True
    assert v["requiere_revision"] is True       # sin Seguridad, la ausencia de alertas no tranquiliza
    assert v["evolucion"]                       # la otra rama completó


def test_si_seguridad_excede_el_timeout_se_continua_sin_ella():
    caso = CASOS[0]

    def lento(_state):
        time.sleep(0.6)
        return {"estado_nodos": {"seguridad": "ok"}}

    grafo, _ = _grafo(caso["edad"], seguridad=lento, timeout_s=0.1)
    v = _correr(grafo, caso).values

    assert v["estado_nodos"]["seguridad"] == "timeout"
    assert v["turno_incompleto"] is True and v["requiere_revision"] is True


def test_si_documentacion_falla_el_turno_queda_incompleto_sin_forzar_revision():
    caso = CASOS[0]                                            # sin alertas
    grafo, _ = _grafo(caso["edad"], documentacion=_roto)
    v = _correr(grafo, caso).values

    assert v["estado_nodos"]["documentacion"] == "error"
    assert v["turno_incompleto"] is True
    assert v["requiere_revision"] is False
    assert not v.get("evolucion")


def test_si_enfermeria_falla_el_flujo_termina_sin_llamar_a_las_ramas():
    ramas = []

    def espia(nombre):
        def nodo(_state):
            ramas.append(nombre)
            return {"estado_nodos": {nombre: "ok"}}
        return nodo

    grafo, _ = _grafo(
        enfermeria=crear_nodo_enfermeria(obtener_edad=lambda _p: None),
        seguridad=espia("seguridad"), documentacion=espia("documentacion"),
    )
    estado = _correr(grafo, CASOS[0])

    assert estado.next == ()
    assert estado.values["estado_nodos"]["enfermeria"] == "error"
    assert ramas == [] and "alertas_actuales" not in estado.values


# --- con_timeout, rutas y Join por separado ---

def test_con_timeout_devuelve_el_resultado_si_llega_a_tiempo():
    assert con_timeout(lambda _s: {"x": 1}, "n", 1.0)({}) == {"x": 1}


def test_con_timeout_marca_timeout():
    out = con_timeout(lambda _s: time.sleep(0.5), "lento", 0.05)({})
    assert out["estado_nodos"] == {"lento": "timeout"} and out["errores"]


def test_con_timeout_captura_excepciones():
    out = con_timeout(_roto, "roto", 1.0)({})
    assert out["estado_nodos"] == {"roto": "error"} and out["errores"]


@pytest.mark.parametrize("state, esperado", [
    ({"estado_nodos": {"seguridad": "ok"}, "alertas_actuales": [object()]}, "marcar_revision"),
    ({"estado_nodos": {"seguridad": "ok"}, "alertas_actuales": []}, "aprobacion"),
    ({"estado_nodos": {"seguridad": "timeout"}, "alertas_actuales": []}, "marcar_revision"),
])
def test_el_edge_condicional_post_join(state, esperado):
    assert ruta_post_join(state) == esperado


@pytest.mark.parametrize("estados, incompleto", [
    ({"seguridad": "ok", "documentacion": "ok"}, False),
    ({"seguridad": "degradado", "documentacion": "ok"}, False),
    ({"seguridad": "timeout", "documentacion": "ok"}, True),
    ({"seguridad": "ok", "documentacion": "error"}, True),
    ({"seguridad": "ok"}, True),
])
def test_el_join_marca_el_turno_incompleto(estados, incompleto):
    assert nodo_join({"estado_nodos": estados})["turno_incompleto"] is incompleto


# --- varias ejecuciones y varios hilos ---

def test_dos_ejecuciones_en_el_mismo_hilo_no_mezclan_las_alertas():
    grafo, _ = _grafo()
    _correr(grafo, _caso("saturacion_baja_y_taquipnea"))
    grafo.invoke(Command(resume={"decision": "aprobado"}), _config())

    v = _correr(grafo, CASOS[0]).values                        # segunda ejecución, sin alertas
    assert v["alertas_actuales"] == []
    assert v["requiere_revision"] is False
    assert len(v["alertas"]) >= 1                              # el acumulado del turno conserva las anteriores


def test_hilos_distintos_no_comparten_estado():
    grafo, _ = _grafo()
    _correr(grafo, _caso("dolor_intenso"), hilo="A")
    _correr(grafo, _caso("hipertension"), hilo="B")

    a = grafo.get_state(_config("A")).values
    b = grafo.get_state(_config("B")).values
    assert {x.tipo_alerta for x in a["alertas_actuales"]} == {"dolor_severo"}
    assert {x.tipo_alerta for x in b["alertas_actuales"]} == {"hipertension"}
