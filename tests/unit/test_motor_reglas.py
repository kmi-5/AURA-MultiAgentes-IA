import copy

import pytest
import yaml

from backend.app.core.motor_reglas import evaluar_seguridad
from backend.app.core.reglas import RUTA_DEFAULT, ConjuntoReglas, cargar_reglas
from backend.app.data.casos_limite import CASOS_LIMITE
from backend.app.data.casos_prueba import CASOS

TODOS = CASOS + CASOS_LIMITE
AVISOS_ESPERADOS = {
    "campos_faltantes": {"news2_parcial", "morse_no_evaluable"},
    "menor_de_16": {"news2_no_aplicable"},
}


def _caso(escenario):
    return next(c for c in TODOS if c["escenario"] == escenario)


def _evaluar(caso, **extra):
    return evaluar_seguridad(edad=caso["edad"], signos=caso["signos"],
                             valoracion_caidas=caso["caidas"], **extra)


@pytest.mark.parametrize("caso", TODOS, ids=lambda c: c["escenario"])
def test_el_motor_coincide_con_el_golden_set(caso):
    r = _evaluar(caso)

    assert {a.regla_id for a in r.alertas} == caso["alertas_esperadas"]
    assert r.version_reglas == cargar_reglas().version

    puntajes = {k: v for k, v in (("news2", caso["news2_esperado"]),
                                  ("morse", caso["morse_esperado"])) if v is not None}
    assert r.puntajes_escalas == puntajes

    assert set(r.avisos) == AVISOS_ESPERADOS.get(caso["escenario"], set())


def test_el_yaml_es_lo_que_excluye_a_los_menores_de_16():
    datos = copy.deepcopy(yaml.safe_load(RUTA_DEFAULT.read_text(encoding="utf-8")))
    for r in datos["reglas"]:
        if r["id"] == "taquipnea":
            del r["edad_minima"]
    sin_restriccion = ConjuntoReglas.model_validate(datos)

    r = _evaluar(_caso("menor_de_16"), reglas=sin_restriccion)
    assert {a.regla_id for a in r.alertas} == {"dolor_severo", "taquipnea"}


def test_sin_escala_2_la_misma_saturacion_dispara_alertas():
    caso = _caso("escala_spo2_2")
    signos = {k: v for k, v in caso["signos"].items() if k != "escala_spo2"}
    r = evaluar_seguridad(edad=caso["edad"], signos=signos, valoracion_caidas=caso["caidas"])
    assert {a.regla_id for a in r.alertas} == {"saturacion_baja", "news2_rojo_unico"}


def test_el_rojo_unico_informa_que_parametros_puntuaron_3():
    r = _evaluar(_caso("hipotension_y_taquicardia"))
    alerta = next(a for a in r.alertas if a.regla_id == "news2_rojo_unico")
    assert set(alerta.observado["parametros_en_3"]) == {"ta_sistolica", "fc"}


def test_sin_datos_no_dispara_alertas_ni_falla():
    r = evaluar_seguridad(edad=40, signos={}, valoracion_caidas=None)
    assert r.alertas == ()
    assert set(r.avisos) == {"news2_parcial", "morse_no_evaluable"}
