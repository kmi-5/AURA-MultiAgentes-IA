from datetime import datetime

from backend.app.data.casos_limite import CASOS_LIMITE
from backend.app.data.casos_prueba import CASOS
from backend.app.graph.consolidar import crear_nodo_consolidar, entrada_historial, generar_pase
from backend.app.models.schemas import Alerta

HORA = datetime(2026, 10, 16, 8, 15)
CAIDOS = {"enfermeria": "ok", "seguridad": "ok", "documentacion": "error"}


def _caso(escenario):
    return next(c for c in CASOS + CASOS_LIMITE if c["escenario"] == escenario)


def test_el_pase_de_un_registro_incluye_lo_esencial(armar_estado):
    e = entrada_historial(armar_estado(_caso("saturacion_baja_y_taquipnea")), HORA)
    pase = generar_pase([e])

    for esperado in ("PASE DE GUARDIA - turno manana", "Registros del turno: 1",
                     "[08:15] Registro 1 (aprobado)", "Signos vitales: TA 110/70",
                     "Evolución: Evolución de prueba.", "news2_alto (alta)",
                     "Escalas: NEWS2 9, Morse 0", "Pendientes al cierre:",
                     "- 10:00 Control de signos vitales"):
        assert esperado in pase


def test_sin_alertas_el_pase_lo_dice(armar_estado):
    e = entrada_historial(armar_estado(_caso("estable_sin_alertas")), HORA)
    assert "Alertas: ninguna." in generar_pase([e])


def test_si_seguridad_fallo_no_se_muestran_alertas_viejas(armar_estado):
    estado = armar_estado(_caso("saturacion_baja_y_taquipnea"),
                          estado_nodos={"enfermeria": "ok", "seguridad": "timeout",
                                        "documentacion": "ok"})
    e = entrada_historial(estado, HORA)
    assert e["alertas"] == [] and e["puntajes"] == {}
    assert "no disponibles (falló el análisis de seguridad)" in generar_pase([e])


def test_si_documentacion_fallo_la_evolucion_figura_como_no_disponible(armar_estado):
    e = entrada_historial(armar_estado(_caso("estable_sin_alertas"), estado_nodos=CAIDOS), HORA)
    assert "Evolución: no disponible." in generar_pase([e])


def test_los_avisos_se_traducen_a_texto_clinico(armar_estado):
    e = entrada_historial(armar_estado(_caso("campos_faltantes")), HORA)
    pase = generar_pase([e])
    assert "NEWS2 calculado con datos incompletos" in pase
    assert "Escala de Morse no evaluable" in pase


def test_el_pase_acumula_los_registros_y_los_pendientes_son_los_del_ultimo(armar_estado):
    e1 = entrada_historial(armar_estado(_caso("saturacion_baja_y_taquipnea"),
                                        idempotency_key="k1"), HORA)
    e2 = entrada_historial(armar_estado(_caso("estable_sin_alertas"), idempotency_key="k2"),
                           datetime(2026, 10, 16, 9, 30))
    pase = generar_pase([e1, e2])

    assert "Registros del turno: 2" in pase
    assert "[08:15] Registro 1" in pase and "[09:30] Registro 2" in pase
    assert pase.count("Pendientes al cierre:") == 1
    assert pase.count("Control de signos vitales") == 1      # solo los del último registro


def test_un_registro_con_la_misma_clave_no_se_repite(armar_estado):
    e = entrada_historial(armar_estado(_caso("estable_sin_alertas")), HORA)
    pase = generar_pase([e, {**e, "hora": "09:00"}])
    assert "Registros del turno: 1" in pase
    assert "[09:00]" in pase and "[08:15]" not in pase


def test_la_edicion_humana_se_conserva_aunque_documentacion_haya_fallado(armar_estado):
    estado = armar_estado(_caso("estable_sin_alertas"), decision="editado",
                          evolucion="Texto humano.", estado_nodos=CAIDOS)
    pase = generar_pase([entrada_historial(estado, HORA)])
    assert "Evolución: Texto humano." in pase and "(editado por la enfermera)" in pase


def test_un_registro_incompleto_indica_que_rama_fallo(armar_estado):
    estado = armar_estado(_caso("estable_sin_alertas"),
                          estado_nodos={"enfermeria": "ok", "seguridad": "timeout",
                                        "documentacion": "ok"})
    e = entrada_historial(estado, HORA)
    assert e["ramas_fallidas"] == ["seguridad"]
    assert "faltan resultados de seguridad" in generar_pase([e])


def test_el_registro_usa_las_alertas_de_esta_ejecucion_y_no_el_acumulado(armar_estado):
    estado = armar_estado(_caso("dolor_intenso"))
    vieja = Alerta(tipo_alerta="vieja", descripcion="de una ejecución anterior",
                   version_reglas="0.0.1")
    estado["alertas"] = estado["alertas_actuales"] + [vieja]
    e = entrada_historial(estado, HORA)
    assert [a["tipo"] for a in e["alertas"]] == ["dolor_severo"]


def test_el_nodo_devuelve_el_registro_y_el_pase(armar_estado):
    out = crear_nodo_consolidar(ahora=lambda: HORA)(armar_estado(_caso("estable_sin_alertas")))
    assert set(out) == {"historial_turno", "pase_guardia", "estado_nodos"}
    assert len(out["historial_turno"]) == 1 and out["historial_turno"][0]["hora"] == "08:15"
    assert "Registros del turno: 1" in out["pase_guardia"]


def test_con_historial_previo_el_nodo_acumula(armar_estado):
    previo = {**entrada_historial(armar_estado(_caso("saturacion_baja_y_taquipnea")), HORA),
              "clave": "otra"}
    estado = armar_estado(_caso("estable_sin_alertas"), historial_turno=[previo])
    out = crear_nodo_consolidar(ahora=lambda: datetime(2026, 10, 16, 9, 30))(estado)

    assert len(out["historial_turno"]) == 1             # solo el nuevo; el reducer suma
    assert "Registros del turno: 2" in out["pase_guardia"]
