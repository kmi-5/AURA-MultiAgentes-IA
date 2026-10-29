"""Pruebas de pantalla con streamlit.testing.v1.AppTest y un cliente falso (sin red)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import api_client as api
import payload as pl

APP = str(Path(__file__).resolve().parents[2] / "frontend" / "app.py")
TIMEOUT = 30


class FakeCliente:
    def __init__(self, **respuestas):
        self.r = respuestas
        self.llamadas = []

    def _resp(self, nombre, *args):
        self.llamadas.append((nombre, *args))
        v = self.r.get(nombre)
        if isinstance(v, Exception):
            raise v
        return v() if callable(v) else v

    def login(self, u, p): return self._resp("login", u, p)
    def listar_pacientes(self): return self._resp("pacientes") or []
    def procesar(self, payload, clave): return self._resp("procesar", payload, clave)
    def consultar_turno(self, t): return self._resp("turno", t)
    def decidir(self, t, d, clave, evol=None, motivo=None): return self._resp("decidir", t, d, evol, clave)
    def pase(self, pid): return self._resp("pase", pid)
    def tareas(self, pid, estado=None): return self._resp("tareas", pid, estado) or []
    def alertas(self, pid): return self._resp("alertas", pid) or []
    def auditoria(self, limite=100): return self._resp("auditoria") or []


TID = "3:manana:2026-10-28"
VISTA = {"thread_id": TID, "estado": "pendiente_aprobacion", "procesado_por": 1, "estado_nodos": {},
         "revision": {
    "evolucion": "Paciente lúcido, refiere disnea leve.", "seguridad_disponible": True, "turno_incompleto": False,
    "alertas": [{"tipo_alerta": "saturacion_baja", "descripcion": "SatO2 85%", "severidad": "alta", "version_reglas": "1.0.0"},
                {"tipo_alerta": "taquipnea", "descripcion": "FR 24", "severidad": "media", "version_reglas": "1.0.0"}],
    "puntajes_escalas": {"news2": 9}, "avisos_seguridad": [], "requiere_revision": True},
    "tareas": [{"tipo": "medicacion", "horario": "08:00"}]}
COMPLETADO = {**VISTA, "estado": "completado"}
DESCARTADO = {**VISTA, "estado": "descartado"}
PERSIST = {**VISTA, "estado": "persistencia_pendiente"}


def pagina(modulo: str, sesion_inicial: dict, cliente: FakeCliente) -> AppTest:
    codigo = f"""
import sys
sys.path.insert(0, {str(Path(APP).parent)!r})
from paginas import {modulo}
{modulo}.mostrar()
"""
    at = AppTest.from_string(codigo, default_timeout=TIMEOUT)
    at.session_state["_cliente"] = cliente
    for k, v in sesion_inicial.items():
        at.session_state[k] = v
    return at


ENF = {"token": "t", "usuario": "enf", "rol": "enfermeria"}
AUD = {"token": "t", "usuario": "aud", "rol": "auditoria"}
SUP = {"token": "t", "usuario": "sup", "rol": "supervision"}


def completar_formulario(at, paciente=3):
    caso = pl.CASOS_DEMO["Saturación baja y taquipnea"]
    at.number_input(key="f_paciente").set_value(paciente)  # sin lista de pacientes: campo numérico
    for k in pl.RANGOS:
        at.number_input(key=f"f_{k}").set_value(caso[k])
    at.radio(key="f_o2").set_value(True)
    at.selectbox(key="f_conciencia").set_value("A")
    c = caso["caidas"]
    at.radio(key="f_c_antecedente").set_value(c["antecedente_caidas"])
    at.radio(key="f_c_diagnostico").set_value(c["diagnostico_secundario"])
    at.radio(key="f_c_via").set_value(c["via_iv"])
    at.radio(key="f_c_ayuda").set_value(c["ayuda_deambular"])
    at.radio(key="f_c_marcha").set_value(c["marcha"])
    at.radio(key="f_c_mental").set_value(c["estado_mental"])
    at.text_area(key="f_obs").set_value(caso["observacion"])
    at.text_area(key="f_med").set_value("08:00")


def boton(at, texto):
    return next(b for b in at.button if b.label == texto)


# ------------------------------------------------------------------ procesar
def test_formulario_no_precarga_signos_vitales():
    at = pagina("procesar", ENF, FakeCliente()).run()
    assert not at.exception
    assert all(at.number_input(key=f"f_{k}").value is None for k in pl.RANGOS)
    assert at.radio(key="f_o2").value is None


def test_enviar_vacio_marca_campos_y_no_llama_a_la_api():
    cli = FakeCliente()
    at = pagina("procesar", ENF, cli).run()
    boton(at, "Procesar turno").click().run()
    assert not at.exception
    assert not [c for c in cli.llamadas if c[0] == "procesar"]
    assert any("Obligatorio" in m.value for m in at.markdown)


def test_envio_exitoso_guarda_pendiente_y_libera_clave():
    cli = FakeCliente(procesar=VISTA)
    at = pagina("procesar", ENF, cli).run()
    completar_formulario(at)
    at.run()
    boton(at, "Procesar turno").click().run()
    assert not at.exception
    llamadas = [c for c in cli.llamadas if c[0] == "procesar"]
    assert len(llamadas) == 1 and len(llamadas[0][2]) == 32
    assert at.session_state["turno_pendiente"]["thread_id"] == TID
    assert "idem_clave" not in at.session_state


def test_422_se_muestra_por_campo():
    err = api.Validacion("x", campos={"observacion": "texto con forma de instrucción"})
    at = pagina("procesar", ENF, FakeCliente(procesar=err)).run()
    completar_formulario(at); at.run()
    boton(at, "Procesar turno").click().run()
    assert any("forma de instrucción" in m.value for m in at.markdown)


def test_reintento_tras_503_reutiliza_la_clave():
    cli = FakeCliente(procesar=api.ServicioNoDisponible("x", 503))
    at = pagina("procesar", ENF, cli).run()
    completar_formulario(at); at.run()
    boton(at, "Procesar turno").click().run()
    boton(at, "Procesar turno").click().run()
    claves = [c[2] for c in cli.llamadas if c[0] == "procesar"]
    assert len(claves) == 2 and claves[0] == claves[1]


def test_409_ofrece_recuperar_el_turno_pendiente():
    cli = FakeCliente(procesar=api.Conflicto("Este paciente-turno tiene un procesamiento pendiente de resolver", 409),
                      turno=VISTA)
    at = pagina("procesar", ENF, cli).run()
    completar_formulario(at, paciente=3); at.run()
    boton(at, "Procesar turno").click().run()
    assert any("pendiente de resolver" in e.value for e in at.error)
    boton(at, "Recuperar el turno pendiente").click().run()
    assert ("turno", pl.thread_id_para(3, at.session_state["f_turno"])) in cli.llamadas
    assert at.session_state["turno_pendiente"]["thread_id"] == TID


def test_auditoria_no_ve_el_formulario():
    at = pagina("procesar", AUD, FakeCliente()).run()
    assert not at.number_input and any("solo lectura" in i.value for i in at.info)


def test_caso_de_prueba_solo_en_dev(monkeypatch):
    monkeypatch.setenv("AURA_ENTORNO", "prod")
    assert not any(b.label == "Cargar caso de prueba" for b in pagina("procesar", ENF, FakeCliente()).run().button)
    monkeypatch.setenv("AURA_ENTORNO", "dev")
    at = pagina("procesar", ENF, FakeCliente()).run()
    boton(at, "Cargar caso de prueba").click().run()
    assert not at.exception and at.number_input(key="f_sato2").value == 98
    assert at.number_input(key="f_paciente").value == 1


# ------------------------------------------------------------------ aprobación
def aprobacion(cli, extra=None, vista=VISTA):
    return pagina("aprobacion", {**ENF, "turno_pendiente": vista, **(extra or {})}, cli).run()


def test_aprobacion_muestra_alertas_con_texto_de_severidad():
    at = aprobacion(FakeCliente())
    textos = " ".join(m.value for m in at.markdown)
    assert "ALTA" in textos and "MEDIA" in textos and "saturacion_baja" in textos


def test_seguridad_no_disponible_se_advierte():
    v = {**VISTA, "revision": {**VISTA["revision"], "seguridad_disponible": False, "alertas": [], "requiere_revision": False}}
    at = aprobacion(FakeCliente(), vista=v)
    assert any("no estuvo disponible" in e.value for e in at.error)


def test_aprobar_envia_clave_y_limpia():
    cli = FakeCliente(decidir=COMPLETADO)
    at = aprobacion(cli)
    boton(at, "Aprobar").click().run()
    nombre, tid, dec, evol, clave = cli.llamadas[-1]
    assert (nombre, tid, dec, evol) == ("decidir", TID, "aprobado", None) and len(clave) == 32
    assert "turno_pendiente" not in at.session_state


def test_editar_manda_la_evolucion_editada():
    cli = FakeCliente(decidir=COMPLETADO)
    at = aprobacion(cli)
    at.text_area(key="evolucion_editada").set_value("Texto corregido por la enfermera.").run()
    boton(at, "Guardar edición y aprobar").click().run()
    assert cli.llamadas[-1][:4] == ("decidir", TID, "editado", "Texto corregido por la enfermera.")


def test_editar_vacio_no_llama_a_la_api():
    cli = FakeCliente(decidir=COMPLETADO)
    at = aprobacion(cli)
    at.text_area(key="evolucion_editada").set_value("  ").run()
    boton(at, "Guardar edición y aprobar").click().run()
    assert not [c for c in cli.llamadas if c[0] == "decidir"]


def test_descartar_exige_confirmacion():
    cli = FakeCliente(decidir=DESCARTADO)
    at = aprobacion(cli)
    assert boton(at, "Descartar").disabled
    at.checkbox(key="confirmar_descarte").check().run()
    boton(at, "Descartar").click().run()
    assert cli.llamadas[-1][:3] == ("decidir", TID, "descartado")
    assert "turno_pendiente" not in at.session_state


def test_409_ya_resuelto_limpia_el_pendiente():
    cli = FakeCliente(decidir=api.Conflicto("El turno no tiene una decisión pendiente", 409), turno=COMPLETADO)
    at = aprobacion(cli)
    boton(at, "Aprobar").click().run()
    assert "turno_pendiente" not in at.session_state


def test_409_en_curso_conserva_el_pendiente():
    cli = FakeCliente(decidir=api.Conflicto("Ya hay una solicitud en curso con esta clave", 409), turno=VISTA)
    at = aprobacion(cli)
    boton(at, "Aprobar").click().run()
    assert "turno_pendiente" in at.session_state


def test_503_reintenta_con_la_misma_clave():
    cli = FakeCliente(decidir=api.ServicioNoDisponible("x", 503), turno=VISTA)
    at = aprobacion(cli)
    boton(at, "Aprobar").click().run()
    boton(at, "Aprobar").click().run()
    claves = [c[4] for c in cli.llamadas if c[0] == "decidir"]
    assert len(claves) == 2 and claves[0] == claves[1]


def test_persistencia_pendiente_reintenta_la_misma_decision_con_clave_nueva():
    respuestas = iter([PERSIST, COMPLETADO])
    cli = FakeCliente(decidir=lambda: next(respuestas))
    at = aprobacion(cli)
    boton(at, "Aprobar").click().run()
    assert at.session_state["turno_pendiente"]["estado"] == "persistencia_pendiente"
    boton(at, "Reintentar guardado").click().run()
    d = [c for c in cli.llamadas if c[0] == "decidir"]
    assert d[1][2] == "aprobado" and d[0][4] != d[1][4]
    assert "turno_pendiente" not in at.session_state


def test_sin_pendiente():
    at = pagina("aprobacion", ENF, FakeCliente()).run()
    assert any("No hay registros" in m.value for m in at.markdown)


# ------------------------------------------------------------------ dashboard
PACIENTES = [{"id": 3, "nombre": "Paciente 03 (Prueba)", "edad": 67, "habitacion": "103"}]


def dash(rol, **resp):
    return pagina("dashboard", rol, FakeCliente(pacientes=PACIENTES, **resp)).run()


def test_dashboard_enfermeria_no_ofrece_auditoria():
    at = dash(ENF, pase=api.NoEncontrado("Sin pase", 404))
    assert not at.exception and "Auditoría" not in at.radio(key="d_vista").options


def test_dashboard_auditoria_no_ve_tareas_pero_si_auditoria():
    at = dash(AUD)
    assert "Tareas pendientes" not in at.radio(key="d_vista").options and "Auditoría" in at.radio(key="d_vista").options


@pytest.mark.parametrize("rol", [SUP, AUD])
def test_dashboard_supervision_y_auditoria_ven_auditoria(rol):
    at = dash(rol, auditoria=[{"usuario_id": 1, "tarea": "turno_aprobado"}])
    at.radio(key="d_vista").set_value("Auditoría").run()
    assert not at.exception and at.dataframe


def test_dashboard_pase_del_paciente():
    at = dash(ENF, pase={"turno": "manana", "contenido_consolidado": "Pase consolidado de prueba", "incompleto": False})
    assert any("Pase consolidado de prueba" in m.value for m in at.markdown)


def test_dashboard_sin_pase_no_rompe():
    at = dash(ENF, pase=api.NoEncontrado("Sin pase", 404))
    assert not at.exception and any("Todavía no hay un pase" in m.value for m in at.markdown)


def test_dashboard_tareas_pide_solo_pendientes():
    cli = FakeCliente(pacientes=PACIENTES, tareas=[{"tipo": "control", "estado": "pendiente"}])
    at = pagina("dashboard", ENF, cli).run()
    at.radio(key="d_vista").set_value("Tareas pendientes").run()
    assert ("tareas", 3, "pendiente") in cli.llamadas and len(at.dataframe[0].value) == 1


def test_dashboard_403_no_rompe():
    at = dash(SUP, auditoria=api.Prohibido("no", 403))
    at.radio(key="d_vista").set_value("Auditoría").run()
    assert not at.exception and any("no tiene acceso" in i.value for i in at.info)


def test_dashboard_alertas_guardadas():
    at = dash(ENF, alertas=[{"tipo_alerta": "hipertension", "estado_revision": "pendiente"}])
    at.radio(key="d_vista").set_value("Alertas").run()
    assert "hipertension" in str(at.dataframe[0].value)


# ------------------------------------------------------------------ app / login / 401
def test_login_correcto_y_menu_por_rol():
    at = AppTest.from_file(APP, default_timeout=TIMEOUT)
    import base64, json
    cuerpo = base64.urlsafe_b64encode(json.dumps({"sub": "3", "nombre": "Auditor Demo", "rol": "auditoria"}).encode()).decode().rstrip("=")
    at.session_state["_cliente"] = FakeCliente(login={"access_token": f"h.{cuerpo}.f", "token_type": "bearer", "expires_in": 3600})
    at.run()
    at.text_input[0].set_value("auditor1"); at.text_input[1].set_value("pw")
    at.button[0].click().run()
    assert not at.exception and at.session_state["rol"] == "auditoria"
    assert at.title[0].value == "Dashboard"
    assert at.session_state["usuario"] == "Auditor Demo"


def test_login_incorrecto():
    at = AppTest.from_file(APP, default_timeout=TIMEOUT)
    at.session_state["_cliente"] = FakeCliente(login=api.NoAutenticado("x", 401))
    at.run()
    at.text_input[0].set_value("x"); at.text_input[1].set_value("y")
    at.button[0].click().run()
    assert any("incorrectos" in e.value for e in at.error)


def test_401_en_una_pantalla_vuelve_al_login():
    at = AppTest.from_file(APP, default_timeout=TIMEOUT)
    at.session_state["_cliente"] = FakeCliente(pacientes=PACIENTES, pase=api.NoAutenticado("venció", 401))
    at.session_state["token"] = "t"; at.session_state["usuario"] = "e"; at.session_state["rol"] = "auditoria"
    at.run()
    assert not at.exception
    assert "token" not in at.session_state
    assert any("sesión venció" in i.value for i in at.info)
