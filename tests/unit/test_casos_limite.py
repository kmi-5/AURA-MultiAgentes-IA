import pytest

from backend.app.core.reglas import cargar_reglas
from backend.app.data.casos_limite import CASOS_LIMITE
from backend.app.data.casos_prueba import CASOS, entrada_de
from backend.app.models.schemas import DatosEntrada

ALERTAS_NEWS2 = {"news2_rojo_unico", "news2_medio", "news2_alto"}


def test_cubren_las_4_situaciones_limite():
    assert {c["escenario"] for c in CASOS_LIMITE} == {
        "rojo_unico_con_total_bajo", "escala_spo2_2", "menor_de_16", "campos_faltantes",
    }


@pytest.mark.parametrize("caso", CASOS_LIMITE, ids=lambda c: c["escenario"])
def test_cada_caso_limite_es_una_entrada_valida(caso):
    DatosEntrada(**entrada_de(caso, paciente_id=1))


def test_todo_id_esperado_existe_como_regla():
    ids = {r.id for r in cargar_reglas().reglas}
    esperados = set().union(*(c["alertas_esperadas"] for c in CASOS_LIMITE))
    assert esperados <= ids, esperados - ids


def test_los_casos_limite_no_se_mezclan_con_el_seed():
    assert not {c["escenario"] for c in CASOS_LIMITE} & {c["escenario"] for c in CASOS}


def test_las_banderas_son_coherentes():
    for c in CASOS_LIMITE:
        if not c["news2_aplicable"]:
            assert c["news2_esperado"] is None, c["escenario"]
            assert not c["alertas_esperadas"] & ALERTAS_NEWS2, c["escenario"]
        if c["caidas"] is None:
            assert c["morse_esperado"] is None, c["escenario"]

def test_las_alertas_esperadas_aplican_a_la_edad_del_caso():
    reglas = cargar_reglas()
    for caso in CASOS_LIMITE + CASOS:
        for id_ in caso["alertas_esperadas"]:
            assert reglas.por_id(id_).aplica_a_edad(caso["edad"]), (caso["escenario"], id_)