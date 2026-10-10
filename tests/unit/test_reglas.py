import copy

import pytest
import yaml
from pydantic import ValidationError

from backend.app.core.reglas import RUTA_DEFAULT, ConjuntoReglas, cargar_reglas


@pytest.fixture
def datos():
    """YAML real, como dict, listo para mutar en cada test."""
    return copy.deepcopy(yaml.safe_load(RUTA_DEFAULT.read_text(encoding="utf-8")))


def _regla(datos, id_):
    return next(r for r in datos["reglas"] if r["id"] == id_)


def test_el_yaml_real_carga_con_12_reglas_unicas():
    c = cargar_reglas()
    assert c.version == "1.1.0"
    assert len(c.reglas) == 12
    assert len({r.id for r in c.reglas}) == 12


def test_umbrales_news2_no_fueron_modificados():
    c = cargar_reglas()
    medio, alto = c.por_id("news2_medio"), c.por_id("news2_alto")
    assert (medio.minimo, medio.maximo) == (5, 6)
    assert (alto.minimo, alto.maximo) == (7, None)
    assert c.por_id("news2_rojo_unico").criterio == "parametro_rojo"


def test_corte_de_morse_por_defecto_es_45():
    assert cargar_reglas().por_id("riesgo_caida").minimo == 45


def test_las_reglas_locales_estan_marcadas_y_sin_validar():
    c = cargar_reglas()
    for id_ in ("dolor_severo", "hipertension"):
        r = c.por_id(id_)
        assert r.fuente == "convencion_local"
        assert r.validada is False
    # las alertas por parámetro son decisión local aunque el corte venga de NEWS2
    assert all(not r.validada for r in c.reglas if r.tipo == "umbral")


def test_saturacion_baja_solo_aplica_con_escala_1():
    assert cargar_reglas().por_id("saturacion_baja").aplica_escala_spo2 == 1


def test_regla_local_no_puede_declararse_validada(datos):
    _regla(datos, "dolor_severo")["validada"] = True
    with pytest.raises(ValidationError):
        ConjuntoReglas.model_validate(datos)


def test_ids_duplicados_se_rechazan(datos):
    datos["reglas"].append(copy.deepcopy(datos["reglas"][0]))
    with pytest.raises(ValidationError, match="repetidos"):
        ConjuntoReglas.model_validate(datos)


def test_un_campo_desconocido_se_rechaza(datos):
    datos["reglas"][4]["umbrall"] = 1
    with pytest.raises(ValidationError):
        ConjuntoReglas.model_validate(datos)


def test_parametro_inexistente_se_rechaza(datos):
    _regla(datos, "taquicardia")["parametro"] = "glucemia"
    with pytest.raises(ValidationError):
        ConjuntoReglas.model_validate(datos)


def test_operador_invalido_se_rechaza(datos):
    _regla(datos, "taquicardia")["operador"] = "=>"
    with pytest.raises(ValidationError):
        ConjuntoReglas.model_validate(datos)


def test_criterio_total_requiere_minimo(datos):
    del _regla(datos, "news2_alto")["minimo"]
    with pytest.raises(ValidationError, match="minimo"):
        ConjuntoReglas.model_validate(datos)


def test_rango_invertido_se_rechaza(datos):
    _regla(datos, "news2_medio")["minimo"] = 9
    with pytest.raises(ValidationError, match="maximo"):
        ConjuntoReglas.model_validate(datos)


def test_version_con_formato_invalido_se_rechaza(datos):
    datos["version"] = "1.0"
    with pytest.raises(ValidationError):
        ConjuntoReglas.model_validate(datos)

IDS_NEWS2 = {"news2_rojo_unico", "news2_medio", "news2_alto", "taquipnea",
             "taquicardia", "bradicardia", "hipotension", "hipertermia", "saturacion_baja"}

def test_las_reglas_derivadas_de_news2_exigen_16_anios_o_mas():
    for r in cargar_reglas().reglas:
        esperado = 16 if r.id in IDS_NEWS2 else None
        assert r.edad_minima == esperado, r.id

def test_aplica_a_edad():
    c = cargar_reglas()
    assert not c.por_id("taquipnea").aplica_a_edad(15)
    assert c.por_id("taquipnea").aplica_a_edad(16)
    assert c.por_id("dolor_severo").aplica_a_edad(12)     # regla local: sin restricción
    assert c.por_id("riesgo_caida").aplica_a_edad(12)     # Morse: sin restricción


@pytest.mark.parametrize("valor", [-1, 121])
def test_edad_minima_fuera_de_rango_se_rechaza(datos, valor):
    _regla(datos, "taquipnea")["edad_minima"] = valor
    with pytest.raises(ValidationError):
        ConjuntoReglas.model_validate(datos)