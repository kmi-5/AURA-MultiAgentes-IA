import pytest
from backend.app.core.reglas import cargar_reglas
from backend.app.data.casos_prueba import CASOS, entrada_de
from backend.app.models.schemas import DatosEntrada

def test_hay_10_casos_con_escenarios_y_habitaciones_unicas():
    assert len(CASOS) == 10
    assert len({c["escenario"] for c in CASOS}) == 10
    assert len({c["habitacion"] for c in CASOS}) == 10


def test_hay_casos_positivos_y_negativos():
    negativos = [c for c in CASOS if not c["alertas_esperadas"]]
    assert len(negativos) >= 3
    assert len(CASOS) - len(negativos) >= 5


@pytest.mark.parametrize("caso", CASOS, ids=lambda c: c["escenario"])
def test_cada_caso_es_una_entrada_valida(caso):
    DatosEntrada(**entrada_de(caso, paciente_id=1))

def test_todo_id_de_alerta_esperado_existe_como_regla():
    ids_reglas = {r.id for r in cargar_reglas().reglas}
    esperados = set().union(*(c["alertas_esperadas"] for c in CASOS))
    assert esperados <= ids_reglas, esperados - ids_reglas


def test_cada_regla_tiene_al_menos_un_caso_positivo():
    esperados = set().union(*(c["alertas_esperadas"] for c in CASOS))
    sin_caso = {r.id for r in cargar_reglas().reglas} - esperados
    assert not sin_caso, f"reglas sin caso en el golden set: {sin_caso}"