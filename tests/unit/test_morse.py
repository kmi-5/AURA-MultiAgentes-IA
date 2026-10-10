import pytest

from backend.app.core.morse import (
    PUNTAJE_MAXIMO, TABLA_MORSE, calcular_morse, puntaje_item,
)
from backend.app.core.reglas import cargar_reglas
from backend.app.data.casos_limite import CASOS_LIMITE
from backend.app.data.casos_prueba import CASOS
from backend.app.models.db_models import ValoracionCaidasRow


@pytest.mark.parametrize("item, valor, esperado", [
    ("antecedente_caidas", False, 0), ("antecedente_caidas", True, 25),
    ("diagnostico_secundario", False, 0), ("diagnostico_secundario", True, 15),
    ("ayuda_deambular", "ninguna_o_asistida", 0),
    ("ayuda_deambular", "baston_muletas_andador", 15),
    ("ayuda_deambular", "se_apoya_en_muebles", 30),
    ("via_iv", False, 0), ("via_iv", True, 20),
    ("marcha", "normal_o_inmovil", 0), ("marcha", "debil", 10), ("marcha", "alterada", 20),
    ("estado_mental", "conoce_limites", 0), ("estado_mental", "olvida_limitaciones", 15),
])
def test_puntaje_de_cada_opcion(item, valor, esperado):
    assert puntaje_item(item, valor) == esperado


def test_puntaje_minimo_y_maximo():
    minimo = {i: min(o, key=o.get) for i, o in TABLA_MORSE.items()}
    maximo = {i: max(o, key=o.get) for i, o in TABLA_MORSE.items()}
    assert calcular_morse(minimo).puntaje == 0
    assert calcular_morse(maximo).puntaje == PUNTAJE_MAXIMO == 125


@pytest.mark.parametrize("item, valor", [
    ("marcha", "rapida"), ("ayuda_deambular", None), ("via_iv", 1)])
def test_valores_invalidos_se_rechazan(item, valor):
    with pytest.raises(ValueError):
        puntaje_item(item, valor)


def test_si_falta_un_item_se_rechaza():
    caso = dict(CASOS[0]["caidas"])
    del caso["marcha"]
    with pytest.raises(ValueError, match="marcha"):
        calcular_morse(caso)


def test_sin_valoracion_no_es_evaluable():
    r = calcular_morse(None)
    assert (r.evaluable, r.puntaje, r.por_item) == (False, None, {})


def test_acepta_objetos_con_value():
    class Marcha:                     # imita al Enum del schema
        value = "alterada"
    assert puntaje_item("marcha", Marcha()) == 20


def test_la_tabla_cubre_las_columnas_de_items_del_modelo():
    columnas = {c.name for c in ValoracionCaidasRow.__table__.columns}
    assert columnas - {"id", "paciente_id", "turno", "timestamp"} == set(TABLA_MORSE)


def test_el_corte_del_yaml_es_alcanzable():
    assert 0 < cargar_reglas().por_id("riesgo_caida").minimo <= PUNTAJE_MAXIMO


@pytest.mark.parametrize("caso", CASOS + CASOS_LIMITE, ids=lambda c: c["escenario"])
def test_morse_coincide_con_el_golden_set(caso):
    r = calcular_morse(caso["caidas"])
    assert r.puntaje == caso["morse_esperado"]
    assert r.evaluable == (caso["caidas"] is not None)


def test_el_corte_de_morse_coincide_con_riesgo_caida_esperado():
    corte = cargar_reglas().por_id("riesgo_caida").minimo
    for caso in CASOS + CASOS_LIMITE:
        puntaje = calcular_morse(caso["caidas"]).puntaje
        esperado = "riesgo_caida" in caso["alertas_esperadas"]
        assert (puntaje is not None and puntaje >= corte) == esperado, caso["escenario"]
