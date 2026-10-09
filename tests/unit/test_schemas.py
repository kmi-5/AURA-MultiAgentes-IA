import pytest
from pydantic import ValidationError

from backend.app.models.schemas import (  # ← copiá tu import real
    DatosEntrada,
    NivelConciencia,
    ValoracionCaidas,
)


def _payload(**override):
    base = dict(
        paciente_id=1,
        turno="manana",
        signos_vitales=dict(
            ta_sistolica=120, ta_diastolica=80, fc=72, fr=16,
            sato2=97, temperatura=36.6, dolor=2,
        ),
    )
    base.update(override)
    return base


def _morse(**override):
    base = dict(
        antecedente_caidas=False,
        diagnostico_secundario=True,
        ayuda_deambular="ninguna_o_asistida",
        via_iv=True,
        marcha="normal_o_inmovil",
        estado_mental="conoce_limites",
    )
    base.update(override)
    return base


def test_payload_sin_campos_nuevos_sigue_valido():
    d = DatosEntrada(**_payload())
    sv = d.signos_vitales
    assert sv.o2_suplementario is None
    assert sv.conciencia is None
    assert sv.escala_spo2 == 1
    assert d.valoracion_caidas is None


def test_payload_con_campos_nuevos():
    p = _payload(valoracion_caidas=_morse())
    p["signos_vitales"].update(o2_suplementario=True, conciencia="C")
    d = DatosEntrada(**p)
    assert d.signos_vitales.conciencia is NivelConciencia.CONFUSION
    assert d.valoracion_caidas.via_iv is True


def test_escala_spo2_solo_1_o_2():
    p = _payload()
    p["signos_vitales"]["escala_spo2"] = 3
    with pytest.raises(ValidationError):
        DatosEntrada(**p)


def test_valoracion_caidas_rechaza_marcha_invalida():
    with pytest.raises(ValidationError):
        ValoracionCaidas(**_morse(marcha="corriendo"))


def test_valoracion_caidas_exige_todos_los_items():
    datos = _morse()
    del datos["via_iv"]
    with pytest.raises(ValidationError):
        ValoracionCaidas(**datos)


def test_conciencia_rechaza_valor_invalido():
    with pytest.raises(ValueError):
        NivelConciencia("X")

def payload(**over):
    base = {
        "paciente_id": 1,
        "turno": "manana",
        "signos_vitales": {"ta_sistolica": 120, "ta_diastolica": 80, "fc": 72, "fr": 16,
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