"""1
`alertas_esperadas` es PROVISORIO hasta fijar las reglas versionadas (Fase 2).
"""

CASOS = [
    {
        "escenario": "estable_sin_alertas",
        "nombre": "Paciente 01 (Prueba)", "edad": 45, "habitacion": "101",
        "signos": dict(ta_sistolica=120, ta_diastolica=80, fc=72, fr=18, sato2=98, temperatura=36.6, dolor=1),
        "observacion": "Lúcido, orientado, deambula sin ayuda.",
        "dispositivos": ["vía periférica MSD"],
        "medicacion": [("Paracetamol", "500 mg", "cada 8 hs", "08:00")],
        "alertas_esperadas": set(),
    },
    {
        "escenario": "riesgo_caida",
        "nombre": "Paciente 02 (Prueba)", "edad": 82, "habitacion": "102",
        "signos": dict(ta_sistolica=135, ta_diastolica=85, fc=88, fr=18, sato2=95, temperatura=36.8, dolor=3),
        "observacion": "Lúcido, refiere mareos al incorporarse. Deambula con andador.",
        "dispositivos": ["vía periférica MSI"],
        "medicacion": [("Enalapril", "10 mg", "cada 12 hs", "08:00"),
                       ("Furosemida", "40 mg", "cada 8 hs", "06:00")],
        "alertas_esperadas": {"riesgo_caida"},
    },
    {
        "escenario": "saturacion_baja_y_taquipnea",
        "nombre": "Paciente 03 (Prueba)", "edad": 67, "habitacion": "103",
        "signos": dict(ta_sistolica=110, ta_diastolica=70, fc=95, fr=24, sato2=85, temperatura=37.0, dolor=2),  # CAMBIO: fr 22 -> 24 (valor claro)
        "observacion": "Disnea leve al hablar. Cánula nasal a 2 L/min.",                                      # CAMBIO: L/hs -> L/min
        "dispositivos": ["cánula nasal"],
        "medicacion": [("Salbutamol", "2 inhalaciones", "cada 8 hs", "08:00")],
        "alertas_esperadas": {"saturacion_baja", "taquipnea"},                                                # CAMBIO: + taquipnea
    },
    {
        "escenario": "hipertermia_taquicardia_y_taquipnea",
        "nombre": "Paciente 04 (Prueba)", "edad": 55, "habitacion": "104",
        "signos": dict(ta_sistolica=125, ta_diastolica=80, fc=125, fr=25, sato2=97, temperatura=38.7, dolor=4),
        "observacion": "Escalofríos. Herida quirúrgica con apósito mojado y exudado hemático.",              # CAMBIO: "exsudado" -> "exudado"
        "dispositivos": ["vía periférica MSD", "drenaje"],
        "medicacion": [("Ceftriaxona", "1 g", "cada 12 hs", "08:00")],
        "alertas_esperadas": {"hipertermia", "taquicardia", "taquipnea"},                                     # CAMBIO: + taquipnea
    },
    {
        "escenario": "hipertension",
        "nombre": "Paciente 05 (Prueba)", "edad": 74, "habitacion": "105",
        "signos": dict(ta_sistolica=185, ta_diastolica=105, fc=80, fr=18, sato2=96, temperatura=36.5, dolor=2),  # CAMBIO: + fr
        "observacion": "Cefalea leve. Lúcido.",
        "dispositivos": ["vía periférica MSI"],
        "medicacion": [("Amlodipina", "5 mg", "cada 24 hs", "08:00")],                                        # CAMBIO: cada 8 -> cada 24 hs
        "alertas_esperadas": {"hipertension"},
    },
    {
        "escenario": "dolor_intenso",
        "nombre": "Paciente 06 (Prueba)", "edad": 38, "habitacion": "106",
        "signos": dict(ta_sistolica=118, ta_diastolica=76, fc=76, fr=18, sato2=99, temperatura=36.4, dolor=8),  # CAMBIO: fc 134 -> 76, + fr
        "observacion": "Refiere dolor intenso en zona de herida. Lúcida.",
        "dispositivos": ["vía periférica MSI"],
        "medicacion": [("Ketorolac", "30 mg", "cada 8 hs", "10:00")],
        "alertas_esperadas": {"dolor_intenso"},
    },
    {
        "escenario": "riesgo_caida_y_bradicardia",
        "nombre": "Paciente 07 (Prueba)", "edad": 90, "habitacion": "107",
        "signos": dict(ta_sistolica=100, ta_diastolica=60, fc=48, fr=16, sato2=94, temperatura=35.8, dolor=2),
        "observacion": "Somnoliento, desorientado en tiempo, espacio y persona. Requiere asistencia para movilizarse.",
        "dispositivos": ["vía periférica MSI", "sonda vesical"],
        "medicacion": [("Omeprazol", "20 mg", "cada 24 hs", "08:00")],
        "alertas_esperadas": {"riesgo_caida", "bradicardia"},
    },
    {
        "escenario": "postquirurgico_estable",
        "nombre": "Paciente 08 (Prueba)", "edad": 29, "habitacion": "108",
        "signos": dict(ta_sistolica=115, ta_diastolica=75, fc=78, fr=18, sato2=98, temperatura=36.7, dolor=0),
        "observacion": "Postoperatorio inmediato, lúcido. Deambula con ayuda mínima.",
        "dispositivos": ["vía periférica MSD", "drenaje"],
        "medicacion": [("Cefazolina", "1 g", "cada 12 hs", "06:00")],
        "alertas_esperadas": set(),
    },
    {
        "escenario": "hipotension_y_taquicardia",
        "nombre": "Paciente 09 (Prueba)", "edad": 63, "habitacion": "109",
        "signos": dict(ta_sistolica=63, ta_diastolica=43, fc=134, fr=18, sato2=94, temperatura=37.4, dolor=5),  # CAMBIO: + fr, sato2 90 -> 94
        "observacion": "Pálida y sudorosa. Lúcida.",
        "dispositivos": ["vía periférica MSD"],
        "medicacion": [("Dipirona", "500 mg", "cada 8 hs", "08:00")],
        "alertas_esperadas": {"hipotension", "taquicardia"},
    },
    {
        "escenario": "medicacion_multiple_sin_alertas",
        "nombre": "Paciente 10 (Prueba)", "edad": 71, "habitacion": "110",
        "signos": dict(ta_sistolica=128, ta_diastolica=82, fc=84, fr=18, sato2=97, temperatura=36.9, dolor=3),
        "observacion": "Lúcido, colaborador.",
        "dispositivos": ["vía periférica MSD"],
        "medicacion": [("Metformina", "850 mg", "cada 12 hs", "08:00"),
                       ("Aspirina", "100 mg", "cada 24 hs", "12:00"),
                       ("Atorvastatina", "20 mg", "cada 24 hs", "20:00")],
        "alertas_esperadas": set(),
    },
]


def entrada_de(caso: dict, paciente_id: int, turno: str = "manana") -> dict:
    """Arma el payload tal como lo enviaría Streamlit (DatosEntrada)."""
    return {
        "paciente_id": paciente_id,
        "turno": turno,
        "signos_vitales": caso["signos"],
        "observacion": caso["observacion"],
        "dispositivos": caso["dispositivos"],
        "medicacion_programada": [hora for _, _, _, hora in caso["medicacion"]],
    }