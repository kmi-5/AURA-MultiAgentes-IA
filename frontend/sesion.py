"""Token, usuario, rol y clave de idempotencia. TODO vive en st.session_state (nunca en URL ni logs)."""
from __future__ import annotations

import base64
import json
import unicodedata
import uuid

import streamlit as st

import api_client
import config

K_TOKEN, K_USUARIO, K_ROL = "token", "usuario", "rol"
K_CLAVE, K_HUELLA = "idem_clave", "idem_huella"
K_CLIENTE_TEST = "_cliente"  # inyección de un cliente falso en los tests de pantalla


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode()
    return s.strip().lower()


def claims_sin_verificar(token: str) -> dict:
    """Lee el payload del JWT SOLO para decorar la UI (nombre/rol). La API valida la firma."""
    try:
        cuerpo = token.split(".")[1]
        cuerpo += "=" * (-len(cuerpo) % 4)
        return json.loads(base64.urlsafe_b64decode(cuerpo))
    except Exception:
        return {}


def iniciar(token: str, usuario: str, rol: str | None = None):
    claims = claims_sin_verificar(token)
    st.session_state[K_TOKEN] = token
    st.session_state[K_USUARIO] = claims.get("nombre") or usuario
    st.session_state[K_ROL] = _norm(rol or claims.get("rol") or "")


def cerrar():
    st.session_state.clear()


def autenticado() -> bool:
    return bool(st.session_state.get(K_TOKEN))


def usuario() -> str:
    return st.session_state.get(K_USUARIO, "")


def rol() -> str:
    return st.session_state.get(K_ROL, "")


def puede_operar() -> bool:
    """Enfermería y supervisión operan; auditoría solo lee. Ayuda de UI: la API decide."""
    return rol() in {"enfermeria", "supervision"}


def ve_auditoria() -> bool:
    return rol() in {"supervision", "auditoria"}


def cliente() -> api_client.ApiClient:
    falso = st.session_state.get(K_CLIENTE_TEST)
    if falso is not None:
        return falso
    return api_client.ApiClient(config.api_url(), st.session_state.get(K_TOKEN),
                                timeout=config.timeout_s())


# ---- Idempotency-Key: una por envío, se conserva hasta una respuesta definitiva
def clave_para(huella_payload: str) -> str:
    """Mismo contenido que el envío anterior sin respuesta definitiva → misma clave (doble click, reintento)."""
    if st.session_state.get(K_HUELLA) == huella_payload and st.session_state.get(K_CLAVE):
        return st.session_state[K_CLAVE]
    st.session_state[K_HUELLA] = huella_payload
    st.session_state[K_CLAVE] = uuid.uuid4().hex
    return st.session_state[K_CLAVE]


def liberar_clave():
    st.session_state.pop(K_CLAVE, None)
    st.session_state.pop(K_HUELLA, None)
