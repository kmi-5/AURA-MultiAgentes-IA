"""Entrada: login y navegación por rol. Correr con:  uv run streamlit run frontend/app.py"""
import streamlit as st

import api_client as api
import config
import sesion
from paginas import aprobacion, dashboard, procesar


def pantalla_login():
    st.title("AURA · Asistencia de enfermería")
    if config.es_dev():
        st.warning("Entorno de desarrollo: datos de prueba.", icon="🧪")
    aviso = st.session_state.pop("aviso_login", None)
    if aviso:
        st.info(aviso)
    with st.form("login"):
        usuario = st.text_input("Usuario")
        clave = st.text_input("Contraseña", type="password")
        enviar = st.form_submit_button("Ingresar", type="primary")
    if not enviar:
        return
    if not usuario or not clave:
        st.error("Completá usuario y contraseña.")
        return
    try:
        resp = sesion.cliente().login(usuario, clave)
    except api.NoAutenticado:
        st.error("Usuario o contraseña incorrectos.")
    except api.ErrorApi as e:
        st.error(e.mensaje)
    else:
        token = resp.get("access_token")
        if not token:
            st.error("La API no devolvió un token.")
            return
        sesion.iniciar(token, usuario, rol=resp.get("rol"))
        st.rerun()


def main():
    st.set_page_config(page_title="AURA", page_icon="🩺", layout="wide")
    if not sesion.autenticado():
        pantalla_login()
        return
    paginas = {}
    if sesion.puede_operar():
        paginas["procesar"] = st.Page(procesar.mostrar, title="Procesar turno", icon="📝", url_path="procesar")
        paginas["aprobacion"] = st.Page(aprobacion.mostrar, title="Aprobación", icon="✅", url_path="aprobacion")
    paginas["dashboard"] = st.Page(dashboard.mostrar, title="Dashboard", icon="📊", url_path="dashboard",
                                   default=not sesion.puede_operar())
    st.session_state["_paginas"] = paginas
    with st.sidebar:
        st.write(f"**{sesion.usuario()}**")
        st.caption(f"Rol: {sesion.rol() or 'sin rol'}")
        if st.button("Cerrar sesión"):
            sesion.cerrar()
            st.rerun()
    st.navigation(list(paginas.values())).run()


if __name__ == "__main__":
    main()
