import inspect

from backend.app.agents.redactor import crear_redactor
from backend.app.agents.seguridad import crear_nodo_seguridad
from backend.app.core import llm
from backend.app.graph.ensamblado import armar_grafo


def _falso(creados):
    def crear(*, modelo, api_key, timeout_s):
        creados.append((modelo, api_key, timeout_s))
        return lambda _prompt: "{}"
    return crear


def _por_defecto(funcion, nombre):
    return inspect.signature(funcion).parameters[nombre].default


def test_cada_agente_usa_su_modelo(monkeypatch):
    monkeypatch.delenv("AURA_MODELO_SEGURIDAD", raising=False)
    monkeypatch.delenv("AURA_MODELO_DOCUMENTACION", raising=False)
    creados = []
    monkeypatch.setattr(llm, "crear_invocador_gemini", _falso(creados))

    redactor_alertas, redactor_evolucion = llm.crear_redactores("clave-falsa")

    assert creados == [(llm.MODELO_SEGURIDAD, "clave-falsa", llm.TIMEOUT_LLM_S),
                       (llm.MODELO_DOCUMENTACION, "clave-falsa", llm.TIMEOUT_LLM_S)]
    assert callable(redactor_alertas) and callable(redactor_evolucion)


def test_los_modelos_se_pueden_cambiar_por_variable_de_entorno(monkeypatch):
    monkeypatch.setenv("AURA_MODELO_SEGURIDAD", "modelo-a")
    monkeypatch.setenv("AURA_MODELO_DOCUMENTACION", "modelo-b")
    creados = []
    monkeypatch.setattr(llm, "crear_invocador_gemini", _falso(creados))

    llm.crear_redactores("clave-falsa")

    assert [c[0] for c in creados] == ["modelo-a", "modelo-b"]

# por si usas difentes modelos
#def test_cada_agente_tiene_un_modelo_distinto_para_repartir_la_cuota():
#    assert llm.MODELO_SEGURIDAD != llm.MODELO_DOCUMENTACION


def test_el_peor_caso_del_redactor_cabe_en_el_timeout_de_la_rama():
    presupuesto = _por_defecto(crear_nodo_seguridad, "presupuesto_redaccion_s")
    intentos = _por_defecto(crear_redactor, "max_intentos")
    espera = _por_defecto(crear_redactor, "espera_base")
    # una redacción que se cuelga: N intentos con timeout + las esperas (1 s, 2 s...) + el jitter
    una_redaccion = (intentos * llm.TIMEOUT_LLM_S
                     + espera * (2 ** (intentos - 1) - 1) + 0.5 * (intentos - 1))
    assert presupuesto + una_redaccion < _por_defecto(armar_grafo, "timeout_s")