import pytest
from pydantic import ValidationError
from backend.app.models.schemas import DatosEntrada

def payload(**over):
    base = {
        "paciente_id": 1,
        "turno": "manana",
        "signos_vitales": {"ta_sistolica": 120, "ta_diastolica": 80, "fc": 72,
                           "sato2": 98, "temperatura": 36.6, "dolor": 1},
        "observacion": "Paciente lúcido, vía periférica en MSD",
        "medicacion_programada": ["08:00", "14:00"],
    }
    base.update(over)
    return base

def test_payload_valido():
    assert DatosEntrada(**payload()).paciente_id == 1

def test_sato2_fuera_de_rango():
    p = payload()
    p["signos_vitales"]["sato2"] = 150
    with pytest.raises(ValidationError):
        DatosEntrada(**p)

def test_ta_invertida():
    p = payload()
    p["signos_vitales"].update(ta_sistolica=80, ta_diastolica=120)
    with pytest.raises(ValidationError):
        DatosEntrada(**p)

def test_observacion_demasiado_larga():
    with pytest.raises(ValidationError):
        DatosEntrada(**payload(observacion="x" * 501))

def test_horario_invalido():
    with pytest.raises(ValidationError):
        DatosEntrada(**payload(medicacion_programada=["25:99"]))
