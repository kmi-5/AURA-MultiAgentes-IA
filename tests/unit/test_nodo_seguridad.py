import pytest

from backend.app.agents.seguridad import MAX_DESCRIPCION, crear_nodo_seguridad
from backend.app.core.reglas import cargar_reglas
from backend.app.data.casos_limite import CASOS_LIMITE
from backend.app.data.casos_prueba import CASOS
from backend.app.models.schemas import (
    Alerta, DatosEstructurados, SignosVitales, ValoracionCaidas,
)

TODOS = CASOS + CASOS_LIMITE
AVISOS_ESPERADOS = {
    "campos_faltantes": {"news2_parcial", "morse_no_evaluable"},
    "menor_de_16": {"news2_no_aplicable"},
}


def _caso(escenario):
    return next(c for c in TODOS if c["escenario"] == escenario)


def _state(caso, edad_payload=None):
    datos = DatosEstructurados(
        paciente_id=1, turno="manana", edad=edad_payload,
        signos_vitales=SignosVitales(**caso["signos"]),
        valoracion_caidas=ValoracionCaidas(**caso["caidas"]) if caso["caidas"] else None,
        observacion=caso["observacion"], dispositivos=caso["dispositivos"],
    )
    return {"paciente_id": 1, "turno": "manana", "datos_estructurados": datos}


def _nodo(caso, **kwargs):
    return crear_nodo_seguridad(obtener_edad=lambda _pid: caso["edad"], **kwargs)


@pytest.mark.parametrize("caso", TODOS, ids=lambda c: c["escenario"])
def test_el_nodo_coincide_con_el_golden_set(caso):
    out = _nodo(caso)(_state(caso))

    assert all(isinstance(a, Alerta) for a in out["alertas"])
    assert {a.tipo_alerta for a in out["alertas"]} == caso["alertas_esperadas"]
    assert {a.version_reglas for a in out["alertas"]} <= {cargar_reglas().version}

    puntajes = {k: v for k, v in (("news2", caso["news2_esperado"]),
                                  ("morse", caso["morse_esperado"])) if v is not None}
    assert out["puntajes_escalas"] == puntajes
    assert set(out["avisos_seguridad"]) == AVISOS_ESPERADOS.get(caso["escenario"], set())
    assert out["estado_nodos"] == {"seguridad": "ok"}


def test_la_severidad_pasa_a_la_alerta():
    caso = _caso("saturacion_baja_y_taquipnea")
    sev = {a.tipo_alerta: a.severidad for a in _nodo(caso)(_state(caso))["alertas"]}
    assert sev["news2_alto"] == "alta"
    assert sev["taquipnea"] == "media"


def test_la_descripcion_base_incluye_el_dato_observado():
    caso = _caso("hipertermia_taquicardia_y_taquipnea")
    alertas = {a.tipo_alerta: a for a in _nodo(caso)(_state(caso))["alertas"]}
    assert "fr=25" in alertas["taquipnea"].descripcion


def test_el_redactor_cambia_el_texto_pero_no_las_alertas():
    caso = _caso("hipotension_y_taquicardia")
    sin = _nodo(caso)(_state(caso))["alertas"]
    con = _nodo(caso, redactor=lambda a: f"Texto redactado de {a.regla_id}")(_state(caso))["alertas"]

    assert [a.tipo_alerta for a in con] == [a.tipo_alerta for a in sin]
    assert all(a.descripcion == f"Texto redactado de {a.tipo_alerta}" for a in con)


def test_si_el_redactor_falla_no_se_pierde_ninguna_alerta():
    caso = _caso("hipotension_y_taquicardia")

    def roto(_alerta):
        raise RuntimeError("Gemini no responde")

    sin = _nodo(caso)(_state(caso))["alertas"]
    con = _nodo(caso, redactor=roto)(_state(caso))["alertas"]
    assert con == sin


@pytest.mark.parametrize("devuelve", ["", "   ", None, "x" * (MAX_DESCRIPCION + 1)])
def test_un_texto_invalido_del_redactor_cae_en_la_descripcion_base(devuelve):
    caso = _caso("dolor_intenso")
    esperado = _nodo(caso)(_state(caso))["alertas"]
    obtenido = _nodo(caso, redactor=lambda _a: devuelve)(_state(caso))["alertas"]
    assert obtenido == esperado


def test_paciente_inexistente_marca_error_y_no_genera_alertas():
    caso = _caso("dolor_intenso")
    nodo = crear_nodo_seguridad(obtener_edad=lambda _pid: None)
    out = nodo(_state(caso))
    assert out["estado_nodos"] == {"seguridad": "error"}
    assert out["errores"] and "alertas" not in out


def test_la_edad_sale_de_la_base_y_no_del_payload():
    caso = _caso("menor_de_16")                       # en la base tiene 12 años
    out = _nodo(caso)(_state(caso, edad_payload=70))   # el payload dice 70
    assert {a.tipo_alerta for a in out["alertas"]} == {"dolor_severo"}
    assert out["avisos_seguridad"] == ["news2_no_aplicable"]
