import copy

import payload as pl

VALORES = copy.deepcopy(pl.CASOS_DEMO["Saturación baja y taquipnea"])


def valores_ok():
    v = {**copy.deepcopy(VALORES), "paciente_id": 3, "turno": "manana"}
    return v


def test_payload_valido_sin_errores():
    p = pl.armar_payload(valores_ok())
    assert pl.validar(p) == {}
    assert p["signos_vitales"]["fc"] == 95 and isinstance(p["signos_vitales"]["fc"], int)
    assert p["medicacion_programada"] == ["08:00"]
    assert p["dispositivos"] == ["cánula nasal"]


def test_forma_coincide_con_datos_entrada():
    p = pl.armar_payload(valores_ok())
    assert set(p) == {"paciente_id", "turno", "signos_vitales", "observacion", "dispositivos",
                      "medicacion_programada", "valoracion_caidas"}
    assert set(p["signos_vitales"]) == {"ta_sistolica", "ta_diastolica", "fc", "fr", "sato2", "temperatura",
                                        "dolor", "o2_suplementario", "conciencia", "escala_spo2"}
    assert set(p["valoracion_caidas"]) == {"antecedente_caidas", "diagnostico_secundario", "ayuda_deambular",
                                           "via_iv", "marcha", "estado_mental"}


def test_campos_vacios_son_obligatorios():
    p = pl.armar_payload({"turno": "manana"})
    e = pl.validar(p)
    assert e["paciente_id"] and e["signos_vitales.fc"] == "Obligatorio."
    assert "signos_vitales.o2_suplementario" in e and "valoracion_caidas.marcha" in e


def test_fuera_de_rango_y_ta():
    v = valores_ok(); v["fc"] = 400; v["ta_sistolica"] = 70; v["ta_diastolica"] = 80
    e = pl.validar(pl.armar_payload(v))
    assert "Fuera de rango" in e["signos_vitales.fc"]
    assert "mayor que la diastólica" in e["signos_vitales.ta_sistolica"]


def test_horarios():
    assert pl.parsear_horarios("8:00, 14:30\n22:05") == ["08:00", "14:30", "22:05"]
    assert pl.parsear_horarios("25:00") == ["25:00"]
    v = valores_ok(); v["medicacion"] = "25:00"
    assert "Horario inválido" in pl.validar(pl.armar_payload(v))["medicacion_programada"]


def test_limites_de_listas_y_texto():
    v = valores_ok(); v["observacion"] = "x" * 501; v["dispositivos"] = "\n".join("d"*3 for _ in range(11))
    e = pl.validar(pl.armar_payload(v))
    assert "observacion" in e and "dispositivos" in e


def test_huella_estable_y_sensible_al_contenido():
    a = pl.armar_payload(valores_ok()); b = pl.armar_payload(valores_ok())
    assert pl.huella(a) == pl.huella(b)
    b["signos_vitales"]["fc"] = 96
    assert pl.huella(a) != pl.huella(b)


def test_turno_por_hora():
    assert [pl.turno_por_hora(h) for h in (6, 13, 14, 21, 22, 3)] == ["manana", "manana", "tarde", "tarde", "noche", "noche"]


def test_todos_los_casos_demo_validan():
    for nombre, caso in pl.CASOS_DEMO.items():
        assert pl.validar(pl.armar_payload({**caso, "paciente_id": 1, "turno": "tarde"})) == {}, nombre


def test_casos_demo_van_con_su_paciente_del_seed():
    assert [pl.CASOS_DEMO[n]["paciente_id"] for n in
            ("Estable, sin alertas", "Riesgo de caída", "Saturación baja y taquipnea")] == [1, 2, 3]


def test_thread_id_para():
    from datetime import date
    assert pl.thread_id_para(3, "manana", date(2026, 10, 28)) == "3:manana:2026-10-28"
