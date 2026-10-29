"""Vista de aprobación: la enfermera valida lo que armó el sistema. Aprobar, editar o descartar."""
from __future__ import annotations

import streamlit as st

import api_client as api
import sesion
from paginas import _comun
from paginas.procesar import K_MSG, K_PEND

K_ACCION = "accion_decision"
K_DEC = "decision_pendiente"   # última decisión enviada: se repite igual si el guardado falla


def _pedir(accion: str):
    st.session_state[K_ACCION] = accion


def _mostrar_revision(rev: dict, tareas: list):
    if rev.get("turno_incompleto"):
        st.warning("**Turno incompleto:** algún agente no respondió. Revisá el registro con más atención.")
    if not rev.get("seguridad_disponible", True):
        st.error("**El Agente Seguridad no estuvo disponible.** La ausencia de alertas acá NO significa que "
                 "no haya riesgos: evaluá al paciente por tu cuenta.")
    elif rev.get("requiere_revision"):
        st.error("Este turno **requiere revisión**: el sistema generó alertas de seguridad.")

    alertas = rev.get("alertas") or []
    st.subheader(f"Alertas de seguridad ({len(alertas)})")
    st.caption("Son avisos de «requiere revisión» basados en reglas. No son diagnósticos.")
    if not alertas:
        st.write("Sin alertas.")
    for a in alertas:
        st.markdown(f"{_comun.etiqueta_severidad(a.get('severidad'))} · **{a.get('tipo_alerta', '')}** — "
                    f"{a.get('descripcion', '')}")
    for aviso in rev.get("avisos_seguridad") or []:
        st.info(f"Aviso del motor: {aviso}")
    puntajes = rev.get("puntajes_escalas") or {}
    if puntajes:
        st.write("**Puntajes:** " + " · ".join(f"{k}: {v}" for k, v in puntajes.items()))
    if tareas:
        st.subheader("Tareas generadas")
        st.dataframe(tareas, hide_index=True, use_container_width=True)


def _refrescar(thread_id: str) -> dict | None:
    """Vuelve a leer el turno desde la API (mejor esfuerzo)."""
    try:
        return sesion.cliente().consultar_turno(thread_id)
    except api.NoAutenticado as e:
        _comun.mostrar_error(e)
    except api.ErrorApi:
        return None


def _aplicar_resultado(resp: dict):
    s = st.session_state
    estado = resp.get("estado")
    if estado == "persistencia_pendiente":
        s[K_PEND] = resp
        s[K_MSG] = ("error", "La decisión se registró pero el guardado quedó pendiente. Usá «Reintentar guardado».")
    elif estado in ("completado", "descartado"):
        s.pop(K_PEND, None)
        s.pop(K_DEC, None)
        s[K_MSG] = ("success", "Registro guardado." if estado == "completado"
                    else "Registro descartado. Podés volver a cargar el turno.")
    else:
        s[K_PEND] = resp
        s[K_MSG] = ("warning", f"El turno sigue en estado «{estado}».")


def _ejecutar(thread_id: str, decision: str, evolucion: str | None):
    s = st.session_state
    if decision == "editado" and not (evolucion or "").strip():
        s[K_MSG] = ("error", "La evolución editada no puede estar vacía.")
        return
    # Una Idempotency-Key por decisión: se reutiliza si el envío no tuvo respuesta definitiva.
    clave = sesion.clave_para(f"decision:{thread_id}:{decision}:{evolucion or ''}")
    s[K_DEC] = {"decision": decision, "evolucion_editada": evolucion}
    try:
        with st.spinner("Guardando…"):
            resp = sesion.cliente().decidir(thread_id, decision, clave, evolucion)
    except api.NoAutenticado as e:
        _comun.mostrar_error(e)
    except api.Conflicto as e:
        sesion.liberar_clave()
        actual = _refrescar(thread_id)
        if actual and actual.get("estado") in ("completado", "descartado"):
            s.pop(K_PEND, None)
            s.pop(K_DEC, None)
            s[K_MSG] = ("warning", f"Este turno ya tenía una decisión ({actual['estado']}). No se guardó nada nuevo.")
        else:
            if actual:
                s[K_PEND] = actual
            s[K_MSG] = ("warning", e.mensaje)
    except (api.ErrorConexion, api.ServicioNoDisponible):
        actual = _refrescar(thread_id)
        if actual:
            s[K_PEND] = actual
        s[K_MSG] = ("error", "No se pudo guardar. Reintentá la misma decisión: no se duplicará el registro.")
    except api.Validacion as e:
        sesion.liberar_clave()
        s[K_MSG] = ("error", "; ".join(e.campos.values()) or e.mensaje)
    except api.ErrorApi as e:
        sesion.liberar_clave()
        s[K_MSG] = ("error", e.mensaje)
    else:
        sesion.liberar_clave()
        _aplicar_resultado(resp)


def mostrar():
    s = st.session_state
    _comun.banner_dev()
    st.title("Aprobación")
    if not sesion.puede_operar():
        st.info("Tu rol es de solo lectura.")
        return
    msg = s.pop(K_MSG, None)
    if msg:
        getattr(st, msg[0])(msg[1])

    resp = s.get(K_PEND)
    if not resp:
        st.write("No hay registros esperando aprobación.")
        return
    thread_id = api.extraer_thread_id(resp)
    if not thread_id:
        st.error("La respuesta de la API no trae el identificador del turno; no se puede decidir.")
        return
    rev = resp.get("revision") or {}
    ocupado = bool(s.get(K_ACCION))
    evol = rev.get("evolucion") or ""

    st.subheader("Evolución de enfermería")
    if not evol:
        st.warning("El sistema no generó la evolución. Podés escribirla en «Editar la evolución».")
    st.text_area("Evolución propuesta", value=evol, disabled=True, height=200, key="evolucion_vista")
    _mostrar_revision(rev, resp.get("tareas") or [])
    st.divider()

    previa = s.get(K_DEC)
    if resp.get("estado") == "persistencia_pendiente" and previa:
        st.button("Reintentar guardado", type="primary", on_click=_pedir, args=("reintentar",), disabled=ocupado)
    else:
        if resp.get("estado") == "persistencia_pendiente":
            st.info("El guardado quedó pendiente. Elegí la MISMA decisión que tomaste antes.")
        st.button("Aprobar", type="primary", on_click=_pedir, args=("aprobado",), disabled=ocupado)
        with st.expander("Editar la evolución antes de aprobar"):
            if "evolucion_editada" not in s:
                s["evolucion_editada"] = evol
            st.text_area("Evolución editada", key="evolucion_editada", height=200)
            st.button("Guardar edición y aprobar", on_click=_pedir, args=("editado",), disabled=ocupado)
        with st.expander("Descartar"):
            st.checkbox("Confirmo que quiero descartar este procesamiento", key="confirmar_descarte")
            st.button("Descartar", on_click=_pedir, args=("descartado",),
                      disabled=ocupado or not s.get("confirmar_descarte"))

    accion = s.get(K_ACCION)
    if accion:
        try:
            if accion == "reintentar":
                _ejecutar(thread_id, previa["decision"], previa["evolucion_editada"])
            else:
                _ejecutar(thread_id, accion, s.get("evolucion_editada") if accion == "editado" else None)
        finally:
            s[K_ACCION] = None
        st.rerun()
