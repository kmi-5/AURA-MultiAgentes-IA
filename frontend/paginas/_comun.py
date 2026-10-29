"""Piezas compartidas por las pantallas."""
from __future__ import annotations

import streamlit as st

import api_client as api
import config
import sesion

SEVERIDAD = {"alta": ("🔴", "ALTA", "red"), "media": ("🟠", "MEDIA", "orange"), "baja": ("🟡", "BAJA", "blue")}


def banner_dev():
    if config.es_dev():
        st.warning("Entorno de desarrollo: datos de prueba, no usar con pacientes reales.", icon="🧪")


def etiqueta_severidad(sev: str | None) -> str:
    """Color Y texto: la severidad nunca depende solo del color."""
    icono, texto, color = SEVERIDAD.get((sev or "media").lower(), ("⚪", str(sev).upper(), "gray"))
    return f"{icono} :{color}[**{texto}**]"


def texto_severidad(sev: str | None) -> str:
    icono, texto, _ = SEVERIDAD.get((sev or "media").lower(), ("⚪", str(sev).upper(), "gray"))
    return f"{icono} {texto}"


def mostrar_error(e: Exception) -> None:
    """Traduce un error de la API a un mensaje. Un 401 cierra la sesión y vuelve al login."""
    if isinstance(e, api.NoAutenticado):
        sesion.cerrar()
        st.session_state["aviso_login"] = "Tu sesión venció. Ingresá de nuevo."
        st.rerun()
    elif isinstance(e, api.Prohibido):
        st.error("Tu rol no tiene permiso para esta acción.")
    elif isinstance(e, api.Conflicto):
        st.warning(f"Conflicto: {e.mensaje}")
    elif isinstance(e, api.ErrorConexion):
        st.error(f"{e.mensaje} Revisá la conexión y reintentá.")
    elif isinstance(e, api.ServicioNoDisponible):
        st.error("El servicio no está disponible. Reintentá en unos segundos.")
    elif isinstance(e, api.ErrorApi):
        st.error(e.mensaje)
    else:
        raise e


def ir_a(nombre: str) -> None:
    paginas = st.session_state.get("_paginas")
    if paginas and nombre in paginas:
        st.switch_page(paginas[nombre])


def pacientes_disponibles() -> list[dict] | None:
    """Lista de pacientes para el selector, cacheada en la sesión. None si la API no la ofrece."""
    if "pacientes" not in st.session_state:
        try:
            st.session_state["pacientes"] = sesion.cliente().listar_pacientes()
        except api.NoAutenticado as e:
            mostrar_error(e)
        except api.ErrorApi:
            st.session_state["pacientes"] = None
    return st.session_state.get("pacientes")


def etiqueta_paciente(p: dict) -> str:
    hab = f" · hab. {p['habitacion']}" if p.get("habitacion") else ""
    return f"{p.get('nombre', 'Paciente')}{hab}"
