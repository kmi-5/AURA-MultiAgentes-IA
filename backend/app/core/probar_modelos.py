"""Prueba qué modelos de Gemini responden con TU clave (paso 2.9). Solo desarrollo.

  uv run python -m backend.app.core.probar_modelos
  uv run python -m backend.app.core.probar_modelos gemini-3.5-flash gemini-3.6-flash
"""
import sys
import time

from ..agents.gemini import crear_invocador_gemini
from .config import settings

CANDIDATOS = [
    "gemini-3.1-pro-preview", "gemini-pro-latest",
    "gemini-3.8-flash", "gemini-3.5-flash", "gemini-flash-latest", "gemini-3.1-flash-lite",
]
PROMPT = 'Respondé únicamente con este JSON: {"descripcion": "listo"}'


def main() -> None:
    for modelo in sys.argv[1:] or CANDIDATOS:
        t0 = time.perf_counter()
        try:
            invocar = crear_invocador_gemini(modelo=modelo, api_key=settings.google_api_key,
                                             timeout_s=60.0)
            respuesta = invocar(PROMPT).strip().replace("\n", " ")
            print(f"OK    {modelo:32s} {time.perf_counter() - t0:5.1f} s  -> {respuesta[:60]}")
        except Exception as e:
            print(f"FALLA {modelo:32s} {time.perf_counter() - t0:5.1f} s  -> {str(e)[:110]}")


if __name__ == "__main__":
    main()
