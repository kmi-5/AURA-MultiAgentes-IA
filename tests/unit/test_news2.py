import pytest

from backend.app.core.news2 import (
    EDAD_MINIMA_NEWS2, calcular_news2, puntaje_conciencia, puntaje_fc, puntaje_fr,
    puntaje_o2, puntaje_spo2_escala1, puntaje_spo2_escala2, puntaje_temperatura,
    puntaje_tas,
)
from backend.app.core.reglas import cargar_reglas
from backend.app.data.casos_limite import CASOS_LIMITE
from backend.app.data.casos_prueba import CASOS


@pytest.mark.parametrize("valor, esperado", [
    (5, 3), (8, 3), (9, 1), (11, 1), (12, 0), (20, 0), (21, 2), (24, 2), (25, 3)])
def test_puntaje_fr(valor, esperado):
    assert puntaje_fr(valor) == esperado


@pytest.mark.parametrize("valor, esperado", [
    (80, 3), (91, 3), (92, 2), (93, 2), (94, 1), (95, 1), (96, 0), (100, 0)])
def test_puntaje_spo2_escala1(valor, esperado):
    assert puntaje_spo2_escala1(valor) == esperado


@pytest.mark.parametrize("sato2, o2, esperado", [
    # al aire
    (80, False, 3), (83, False, 3), (84, False, 2), (85, False, 2), (86, False, 1),
    (87, False, 1), (88, False, 0), (92, False, 0), (93, False, 0), (97, False, 0),
    # con O2 suplementario
    (83, True, 3), (87, True, 1), (88, True, 0), (92, True, 0), (93, True, 1),
    (94, True, 1), (95, True, 2), (96, True, 2), (97, True, 3), (100, True, 3)])
def test_puntaje_spo2_escala2(sato2, o2, esperado):
    assert puntaje_spo2_escala2(sato2, o2) == esperado


@pytest.mark.parametrize("sato2, esperado", [(90, 0), (92, 0), (93, None), (97, None)])
def test_spo2_escala2_sin_dato_de_o2(sato2, esperado):
    assert puntaje_spo2_escala2(sato2, None) == esperado


def test_puntaje_o2():
    assert puntaje_o2(True) == 2
    assert puntaje_o2(False) == 0


@pytest.mark.parametrize("valor, esperado", [
    (70, 3), (90, 3), (91, 2), (100, 2), (101, 1), (110, 1), (111, 0), (219, 0),
    (220, 3), (260, 3)])
def test_puntaje_tas(valor, esperado):
    assert puntaje_tas(valor) == esperado


@pytest.mark.parametrize("valor, esperado", [
    (30, 3), (40, 3), (41, 1), (50, 1), (51, 0), (90, 0), (91, 1), (110, 1),
    (111, 2), (130, 2), (131, 3), (160, 3)])
def test_puntaje_fc(valor, esperado):
    assert puntaje_fc(valor) == esperado


@pytest.mark.parametrize("nivel, esperado", [("A", 0), ("C", 3), ("V", 3), ("P", 3), ("U", 3)])
def test_puntaje_conciencia(nivel, esperado):
    assert puntaje_conciencia(nivel) == esperado


def test_conciencia_invalida_se_rechaza():
    with pytest.raises(ValueError):
        puntaje_conciencia("X")


def test_conciencia_acepta_objetos_con_value():
    class Nivel:                      # imita al Enum del schema
        value = "V"
    assert puntaje_conciencia(Nivel()) == 3


@pytest.mark.parametrize("valor, esperado", [
    (34.0, 3), (35.0, 3), (35.1, 1), (36.0, 1), (36.1, 0), (38.0, 0),
    (38.1, 1), (39.0, 1), (39.1, 2), (40.5, 2)])
def test_puntaje_temperatura(valor, esperado):
    assert puntaje_temperatura(valor) == esperado


_NORMAL = dict(fr=16, sato2=98, ta_sistolica=120, fc=70, temperatura=36.8,
               o2_suplementario=False, conciencia="A")


def test_menores_de_16_no_aplican():
    menor = calcular_news2(edad=15, **_NORMAL)
    assert (menor.aplicable, menor.puntaje, menor.rojo_unico) == (False, None, False)
    assert calcular_news2(edad=EDAD_MINIMA_NEWS2, **_NORMAL).aplicable is True


def test_escala_spo2_invalida_se_rechaza():
    with pytest.raises(ValueError):
        calcular_news2(edad=40, escala_spo2=3, **_NORMAL)


def test_edad_minima_coincide_con_el_yaml():
    reglas = cargar_reglas()
    for id_ in ("news2_rojo_unico", "news2_medio", "news2_alto"):
        assert reglas.por_id(id_).edad_minima == EDAD_MINIMA_NEWS2


def _news2(caso):
    s = caso["signos"]
    return calcular_news2(
        edad=caso["edad"], fr=s["fr"], sato2=s["sato2"], ta_sistolica=s["ta_sistolica"],
        fc=s["fc"], temperatura=s["temperatura"],
        o2_suplementario=s.get("o2_suplementario"), conciencia=s.get("conciencia"),
        escala_spo2=s.get("escala_spo2"))


@pytest.mark.parametrize("caso", CASOS + CASOS_LIMITE, ids=lambda c: c["escenario"])
def test_news2_coincide_con_el_golden_set(caso):
    r = _news2(caso)
    assert r.aplicable == caso.get("news2_aplicable", True)
    assert r.puntaje == caso["news2_esperado"]
    assert r.parcial == caso.get("calculo_parcial", False)
    assert r.rojo_unico == ("news2_rojo_unico" in caso["alertas_esperadas"])


def test_campos_faltantes_se_informan():
    caso = next(c for c in CASOS_LIMITE if c["escenario"] == "campos_faltantes")
    assert _news2(caso).faltantes == ("o2_suplementario", "conciencia")
