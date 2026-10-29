"""Formulario de turno. Sin valores clínicos precargados: todo dato vital se ingresa a propósito."""
from __future__ import annotations

import streamlit as st

import api_client as api
import config
import payload as pl
import sesion
from paginas import _comun

K_PEND = "turno_pendiente"
K_ERR = "errores_form"
K_MSG = "mensaje_form"
K_RECUPERABLE = "turno_recuperable"


def _err(campo: str):
    msg = st.session_state.get(K_ERR, {}).get(campo)
    if msg:
        st.markdown(f":red[⚠ {msg}]")


def _cargar_caso():
    caso = pl.CASOS_DEMO[st.session_state["f_caso"]]
    ids = {p["id"] for p in (st.session_state.get("pacientes") or [])}
    if not ids or caso["paciente_id"] in ids:   # el selector solo acepta ids que existen
        st.session_state["f_paciente"] = caso["paciente_id"]
    for k in pl.RANGOS:
        st.session_state[f"f_{k}"] = caso[k]
    st.session_state["f_o2"] = caso["o2_suplementario"]
    st.session_state["f_conciencia"] = caso["conciencia"]
    st.session_state["f_escala"] = caso["escala_spo2"]
    st.session_state["f_obs"] = caso["observacion"]
    st.session_state["f_disp"] = caso["dispositivos"]
    st.session_state["f_med"] = caso["medicacion"]
    c = caso["caidas"]
    st.session_state["f_c_antecedente"] = c["antecedente_caidas"]
    st.session_state["f_c_diagnostico"] = c["diagnostico_secundario"]
    st.session_state["f_c_ayuda"] = c["ayuda_deambular"]
    st.session_state["f_c_via"] = c["via_iv"]
    st.session_state["f_c_marcha"] = c["marcha"]
    st.session_state["f_c_mental"] = c["estado_mental"]
    st.session_state[K_ERR] = {}


def _iniciar_envio():
    st.session_state["procesando"] = True


def _valores() -> dict:
    s = st.session_state
    return {
        "paciente_id": s.get("f_paciente"), "turno": s.get("f_turno"),
        **{k: s.get(f"f_{k}") for k in pl.RANGOS},
        "o2_suplementario": s.get("f_o2"), "conciencia": s.get("f_conciencia"),
        "escala_spo2": s.get("f_escala", 1),
        "observacion": s.get("f_obs"), "dispositivos": s.get("f_disp"), "medicacion": s.get("f_med"),
        "caidas": {
            "antecedente_caidas": s.get("f_c_antecedente"), "diagnostico_secundario": s.get("f_c_diagnostico"),
            "ayuda_deambular": s.get("f_c_ayuda"), "via_iv": s.get("f_c_via"),
            "marcha": s.get("f_c_marcha"), "estado_mental": s.get("f_c_mental"),
        },
    }


def _enviar():
    s = st.session_state
    payload = pl.armar_payload(_valores())
    errores = pl.validar(payload)
    if errores:
        s[K_ERR] = errores
        s[K_MSG] = ("error", "Revisá los campos marcados antes de procesar.")
        return
    s[K_ERR] = {}
    clave = sesion.clave_para(pl.huella(payload))
    try:
        with st.spinner("Procesando turno… puede tardar hasta un minuto si el servicio de IA está lento."):
            resp = sesion.cliente().procesar(payload, clave)
    except api.Validacion as e:
        sesion.liberar_clave()
        s[K_ERR] = e.campos
        s[K_MSG] = ("error", "La API rechazó algunos datos. Corregí los campos marcados." if e.campos else e.mensaje)
    except api.NoAutenticado as e:
        _comun.mostrar_error(e)
    except api.Conflicto as e:
        # En curso, o ya hay un procesamiento pendiente para este paciente y turno (quizá de otra sesión).
        s[K_MSG] = ("error", e.mensaje)
        s[K_RECUPERABLE] = (payload["paciente_id"], payload["turno"])
    except (api.ErrorConexion, api.ServicioNoDisponible):
        # Respuesta NO definitiva: se conserva la clave; reintentar no duplica el registro.
        s[K_MSG] = ("error", "No se pudo completar el envío. Podés reintentar: no se duplicará el registro.")
    except api.ErrorApi as e:
        s[K_MSG] = ("error", e.mensaje)
    else:
        sesion.liberar_clave()
        s.pop(K_RECUPERABLE, None)
        _tomar_turno(resp)


def _tomar_turno(resp: dict):
    """Deja el turno listo para decidir, o informa si ya estaba resuelto."""
    s = st.session_state
    if resp.get("estado") in ("pendiente_aprobacion", "persistencia_pendiente"):
        s[K_PEND] = resp
        s[K_MSG] = ("success", "Turno procesado. Revisá y aprobá el registro en «Aprobación».")
    else:
        s[K_MSG] = ("success", f"Este turno ya estaba resuelto (estado: {resp.get('estado')}). No se duplicó nada.")


def _recuperar():
    s = st.session_state
    pid, turno = s[K_RECUPERABLE]
    try:
        resp = sesion.cliente().consultar_turno(pl.thread_id_para(pid, turno))
    except api.NoAutenticado as e:
        _comun.mostrar_error(e)
        return
    except api.ErrorApi as e:
        s[K_MSG] = ("error", f"No se pudo recuperar el turno pendiente: {e.mensaje}")
        return
    s.pop(K_RECUPERABLE, None)
    _tomar_turno(resp)


def mostrar():
    s = st.session_state
    _comun.banner_dev()
    st.title("Procesar turno")
    if not sesion.puede_operar():
        st.info("Tu rol es de solo lectura. Podés ver el pase y la auditoría en el Dashboard.")
        return

    if s.get(K_PEND):
        st.info("Hay un registro esperando aprobación. Resolvelo antes de procesar otro turno.")
        if st.button("Ir a Aprobación"):
            _comun.ir_a("aprobacion")
    if s.get(K_RECUPERABLE) and not s.get(K_PEND):
        if st.button("Recuperar el turno pendiente"):
            _recuperar()
            st.rerun()
    tipo_msg = s.pop(K_MSG, None)
    if tipo_msg:
        (st.success if tipo_msg[0] == "success" else st.error)(tipo_msg[1])

    ocupado = bool(s.get("procesando"))

    if config.es_dev():
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        c1.selectbox("Caso de prueba", list(pl.CASOS_DEMO), key="f_caso")
        c2.button("Cargar caso de prueba", on_click=_cargar_caso, disabled=ocupado)

    st.subheader("Paciente y turno")
    pacientes = _comun.pacientes_disponibles()
    c1, c2 = st.columns(2)
    if pacientes:
        por_id = {p["id"]: p for p in pacientes}
        c1.selectbox("Paciente", list(por_id), index=None, key="f_paciente", placeholder="Elegí un paciente",
                     format_func=lambda i: _comun.etiqueta_paciente(por_id[i]))
    else:
        c1.number_input("ID de paciente", min_value=1, step=1, value=None, key="f_paciente")
    c2.selectbox("Turno", list(pl.TURNOS), format_func=pl.TURNOS.get, key="f_turno",
                 index=list(pl.TURNOS).index(pl.turno_actual()))
    with c1:
        _err("paciente_id")
    with c2:
        _err("turno")

    st.subheader("Signos vitales")
    cols = st.columns(4)
    for i, campo in enumerate(("ta_sistolica", "ta_diastolica", "fc", "fr", "sato2", "temperatura", "dolor")):
        with cols[i % 4]:
            if campo == "temperatura":
                st.number_input(pl.ETIQUETAS[campo], value=None, step=0.1, format="%.1f", key=f"f_{campo}")
            else:
                st.number_input(pl.ETIQUETAS[campo], value=None, step=1, key=f"f_{campo}")
            _err(f"signos_vitales.{campo}")
    with cols[3]:
        st.radio("Oxígeno suplementario", [True, False], index=None, horizontal=True, key="f_o2",
                 format_func=lambda b: "Sí" if b else "No")
        _err("signos_vitales.o2_suplementario")
    st.selectbox("Nivel de conciencia (ACVPU)", list(pl.CONCIENCIA), index=None, key="f_conciencia",
                 format_func=pl.CONCIENCIA.get, placeholder="Elegí una opción")
    _err("signos_vitales.conciencia")
    st.selectbox("Escala de SpO₂", [1, 2], key="f_escala",
                 help="La escala 2 se usa solo por indicación de un clínico (p. ej. EPOC hipercápnico).")

    st.subheader("Observación, dispositivos y medicación")
    st.text_area(f"Observación clínica (máx. {pl.MAX_OBS} caracteres)", key="f_obs", max_chars=pl.MAX_OBS)
    _err("observacion")
    st.text_area("Dispositivos presentes (uno por línea)", key="f_disp")
    _err("dispositivos")
    st.text_area("Horarios de medicación programada (HH:MM, separados por coma o línea)", key="f_med")
    _err("medicacion_programada")

    st.subheader("Valoración de caídas (Morse)")
    c1, c2, c3 = st.columns(3)
    for col, clave, etiqueta, campo in (
        (c1, "f_c_antecedente", "Caída en esta internación o últimos 3 meses (25)", "antecedente_caidas"),
        (c2, "f_c_diagnostico", "Más de un diagnóstico médico (15)", "diagnostico_secundario"),
        (c3, "f_c_via", "Vía IV o heparinizada (20)", "via_iv"),
    ):
        with col:
            st.radio(etiqueta, [True, False], index=None, horizontal=True, key=clave,
                     format_func=lambda b: "Sí" if b else "No")
            _err(f"valoracion_caidas.{campo}")
    for clave, etiqueta, opciones, campo in (
        ("f_c_ayuda", "Ayuda para deambular", pl.AYUDA, "ayuda_deambular"),
        ("f_c_marcha", "Marcha", pl.MARCHA, "marcha"),
        ("f_c_mental", "Estado mental", pl.ESTADO_MENTAL, "estado_mental"),
    ):
        st.radio(etiqueta, list(opciones), index=None, key=clave, format_func=opciones.get, horizontal=True)
        _err(f"valoracion_caidas.{campo}")
    st.caption("El puntaje lo calcula el sistema; acá solo se cargan los ítems.")

    st.button("Procesar turno", type="primary", on_click=_iniciar_envio, disabled=ocupado)
    if ocupado:
        try:
            _enviar()
        finally:
            s["procesando"] = False
        st.rerun()
