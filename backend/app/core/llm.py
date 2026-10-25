"""Redactores reales con Gemini. Un modelo por agente."""
import os
from ..agents.documentacion import crear_redactor_evolucion
from ..agents.gemini import crear_invocador_gemini
from ..agents.redactor import crear_redactor

# Plan gratuito: los modelos Pro dan 429 (sin cuota) y gemini-3.8-flash daba 504 el 24/10/2026.
MODELO_SEGURIDAD = "gemini-3.1-flash-lite"
MODELO_DOCUMENTACION = "gemini-3.1-flash-lite"
TIMEOUT_LLM_S = 10.0


def crear_redactores(api_key: str):
    """Devuelve (redactor_alertas, redactor_evolucion) listos para armar_grafo()."""
    modelo_seguridad = os.getenv("AURA_MODELO_SEGURIDAD", MODELO_SEGURIDAD)
    modelo_documentacion = os.getenv("AURA_MODELO_DOCUMENTACION", MODELO_DOCUMENTACION)
    invocar_seguridad = crear_invocador_gemini(
        modelo=modelo_seguridad, api_key=api_key, timeout_s=TIMEOUT_LLM_S)
    invocar_documentacion = crear_invocador_gemini(
        modelo=modelo_documentacion, api_key=api_key, timeout_s=TIMEOUT_LLM_S)
    return crear_redactor(invocar_seguridad), crear_redactor_evolucion(invocar_documentacion)