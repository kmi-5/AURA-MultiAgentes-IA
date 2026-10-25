"""Nodos de control y rutas del grafo (paso 2.5)."""
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as TiempoVencido

from langgraph.graph import END

logger = logging.getLogger(__name__)

# "degradado" = el LLM falló pero se usó el fallback determinista: el resultado es válido
ESTADOS_OK = ("ok", "degradado")


def _estado(state: dict, nodo: str) -> str | None:
    return (state.get("estado_nodos") or {}).get(nodo)


def seguridad_ok(state: dict) -> bool:
    return _estado(state, "seguridad") in ESTADOS_OK


def documentacion_ok(state: dict) -> bool:
    return _estado(state, "documentacion") in ESTADOS_OK


def con_timeout(nodo: Callable[[dict], dict], nombre: str, segundos: float):
    """Acota una rama paralela. Si vence o falla, devuelve un estado de error y el Join sigue.

    El hilo vencido no se puede matar, pero su resultado se descarta (los nodos no mutan estado).
    """
    def envuelto(state: dict) -> dict:
        ejecutor = ThreadPoolExecutor(max_workers=1)
        futuro = ejecutor.submit(nodo, state)
        try:
            return futuro.result(timeout=segundos)
        except TiempoVencido:
            logger.warning("Timeout en el nodo %s tras %s s", nombre, segundos)
            return {"errores": [f"{nombre}: timeout tras {segundos} s"],
                    "estado_nodos": {nombre: "timeout"}}
        except Exception:
            logger.exception("Falla inesperada en el nodo %s", nombre)
            return {"errores": [f"{nombre}: error inesperado"],
                    "estado_nodos": {nombre: "error"}}
        finally:
            ejecutor.shutdown(wait=False, cancel_futures=True)

    return envuelto


def nodo_join(state: dict) -> dict:
    fallidas = [n for n in ("seguridad", "documentacion") if _estado(state, n) not in ESTADOS_OK]
    return {
        "turno_incompleto": bool(fallidas),
        "requiere_revision": False,          # lo pone en True marcar_revision
        "estado_nodos": {"join": "parcial" if fallidas else "ok"},
    }


def nodo_marcar_revision(state: dict) -> dict:
    return {"requiere_revision": True}


def ruta_post_enfermeria(state: dict):
    if _estado(state, "enfermeria") != "ok":
        return END                           # sin datos estructurados no hay nada que procesar
    return ["seguridad", "documentacion"]    # fan-out paralelo


def ruta_post_join(state: dict) -> str:
    # Sin Seguridad, la ausencia de alertas no tranquiliza: se pide revisión igual
    if not seguridad_ok(state) or state.get("alertas_actuales"):
        return "marcar_revision"
    return "aprobacion"


def ruta_post_aprobacion(state: dict) -> str:
    # "descartado" no consolida: persistencia solo deja el registro de auditoría
    return "persistencia" if state.get("decision_humana") == "descartado" else "consolidar"
