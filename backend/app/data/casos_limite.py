"""Casos límite del golden set. NO se siembran en Neon.

Cada caso fija una decisión de diseño del motor:
- rojo_unico_con_total_bajo: un parámetro puntúa 3 aunque el total sea bajo (RCP 2017).
- escala_spo2_2: con escala 2 (objetivo 88-92 %) la misma SpO2 puntúa distinto.
- menor_de_16: NEWS2 no aplica; no se calcula ni se evalúan las reglas derivadas de NEWS2.
- campos_faltantes: se calcula con lo disponible y se marca "cálculo parcial".

Campos extra respecto de CASOS:
- news2_aplicable: False si NEWS2 no corresponde (menor de 16).
- calculo_parcial: True si faltan datos y el puntaje es solo una cota inferior.
- news2_esperado / morse_esperado: None si no se pueden calcular.
`alertas_esperadas` corresponde a reglas_seguridad.yaml (ver version en el YAML).
"""

_CAIDAS_BASE = dict(antecedente_caidas=False, diagnostico_secundario=False,
                    ayuda_deambular="ninguna_o_asistida", via_iv=True,
                    marcha="normal_o_inmovil", estado_mental="conoce_limites")

CASOS_LIMITE = [
    {
        # Solo la temperatura (34.8 ºC) puntúa 3. Total NEWS2 = 3 (bajo), pero
        # rojo único exige respuesta urgente igual.
        "escenario": "rojo_unico_con_total_bajo",
        "edad": 50,
        "signos": dict(ta_sistolica=120, ta_diastolica=80, fc=70, fr=16, sato2=97,
                       temperatura=34.8, dolor=1, o2_suplementario=False, conciencia="A"),
        "caidas": dict(_CAIDAS_BASE),
        "observacion": "Lúcido, refiere frío.",
        "dispositivos": ["vía periférica MSD"],
        "medicacion": [("Paracetamol", "500 mg", "cada 8 hs", "08:00")],
        "news2_aplicable": True, "calculo_parcial": False,
        "news2_esperado": 3, "morse_esperado": 20,
        "alertas_esperadas": {"news2_rojo_unico"},
    },
    {
        # SpO2 90 % al aire. Con escala 1 puntuaría 3 (<=91) y dispararía
        # saturacion_baja + news2_rojo_unico; con escala 2 (88-92) puntúa 0.
        "escenario": "escala_spo2_2",
        "edad": 68,
        "signos": dict(ta_sistolica=125, ta_diastolica=80, fc=80, fr=18, sato2=90,
                       temperatura=36.7, dolor=2, o2_suplementario=False, conciencia="A",
                       escala_spo2=2),
        "caidas": dict(_CAIDAS_BASE, diagnostico_secundario=True, via_iv=False),
        "observacion": "Paciente con EPOC, lúcido, sin disnea en reposo.",
        "dispositivos": [],
        "medicacion": [("Tiotropio", "18 mcg", "cada 24 hs", "08:00")],
        "news2_aplicable": True, "calculo_parcial": False,
        "news2_esperado": 0, "morse_esperado": 15,
        "alertas_esperadas": set(),
    },
    {
        # NEWS2 no aplica a menores de 16: ni puntaje ni reglas derivadas de NEWS2
        # (FR 26 y FC 125 NO deben disparar taquipnea/taquicardia). dolor_severo sigue
        # vigente porque es regla local. Morse se calcula igual.
        "escenario": "menor_de_16",
        "edad": 12,
        "signos": dict(ta_sistolica=110, ta_diastolica=70, fc=125, fr=26, sato2=98,
                       temperatura=37.0, dolor=8, o2_suplementario=False, conciencia="A"),
        "caidas": dict(_CAIDAS_BASE),
        "observacion": "Dolor intenso en miembro inferior, lúcido.",
        "dispositivos": ["vía periférica MSI"],
        "medicacion": [("Ibuprofeno", "400 mg", "cada 8 hs", "08:00")],
        "news2_aplicable": False, "calculo_parcial": False,
        "news2_esperado": None, "morse_esperado": 20,
        "alertas_esperadas": {"dolor_severo"},
    },
    {
        # Sin o2_suplementario, sin conciencia y sin valoración de caídas.
        # NEWS2 parcial: FR 22 (2) + SpO2 94 (1) + TAS 105 (1) + FC 100 (1) = 5,
        # una cota inferior ("al menos 5"). Morse no evaluable.
        "escenario": "campos_faltantes",
        "edad": 60,
        "signos": dict(ta_sistolica=105, ta_diastolica=65, fc=100, fr=22, sato2=94,
                       temperatura=36.9, dolor=2),
        "caidas": None,
        "observacion": "Lúcido, colaborador.",
        "dispositivos": ["vía periférica MSD"],
        "medicacion": [("Omeprazol", "20 mg", "cada 24 hs", "08:00")],
        "news2_aplicable": True, "calculo_parcial": True,
        "news2_esperado": 5, "morse_esperado": None,
        "alertas_esperadas": {"taquipnea", "news2_medio"},
    },
]
