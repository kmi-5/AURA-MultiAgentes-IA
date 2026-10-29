"""Dashboard: pase de guardia, tareas pendientes, alertas y auditoría (según rol)."""
from __future__ import annotations

import streamlit as st

import api_client as api
import sesion
from paginas import _comun


def _tabla(filas: list, vacio: str):
    if filas:
        st.dataframe(filas, hide_index=True, use_container_width=True)
    else:
        st.write(vacio)


def _vistas() -> list[str]:
    v = ["Pase de guardia", "Alertas"]
    if sesion.puede_operar():          # la API solo da tareas a enfermería y supervisión
        v.insert(1, "Tareas pendientes")
    if sesion.ve_auditoria():
        v.append("Auditoría")
    return v


def mostrar():
    _comun.banner_dev()
    st.title("Dashboard")
    vistas = _vistas()
    vista = st.radio("Vista", vistas, horizontal=True, key="d_vista")

    paciente_id = None
    if vista != "Auditoría":
        pacientes = _comun.pacientes_disponibles()
        if pacientes:
            por_id = {p["id"]: p for p in pacientes}
            paciente_id = st.selectbox("Paciente", list(por_id), key="d_paciente",
                                       format_func=lambda i: _comun.etiqueta_paciente(por_id[i]))
        else:
            paciente_id = st.number_input("ID de paciente", min_value=1, step=1, value=None, key="d_paciente")
        if not paciente_id:
            st.info("Elegí un paciente.")
            return
    st.button("Actualizar")

    cli = sesion.cliente()
    try:
        if vista == "Pase de guardia":
            try:
                p = cli.pase(paciente_id)
            except api.NoEncontrado:
                st.write("Todavía no hay un pase de guardia guardado para este paciente.")
            else:
                st.markdown(f"**Turno {p.get('turno', '')}** · {p.get('timestamp_generacion', '')}")
                if p.get("incompleto"):
                    st.warning("Este pase se generó con un turno incompleto.")
                st.markdown(p.get("contenido_consolidado", ""))
        elif vista == "Tareas pendientes":
            _tabla(cli.tareas(paciente_id, estado="pendiente"), "No hay tareas pendientes.")
        elif vista == "Alertas":
            st.caption("Avisos de «requiere revisión» guardados. No son diagnósticos.")
            _tabla(cli.alertas(paciente_id), "No hay alertas registradas.")
        else:
            _tabla(cli.auditoria(), "Sin registros de auditoría.")
    except api.Prohibido:
        st.info("Tu rol no tiene acceso a esta vista.")
    except api.ErrorApi as e:
        _comun.mostrar_error(e)
