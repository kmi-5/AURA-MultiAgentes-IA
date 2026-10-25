"""Consolidación del turno y pase de guardia (paso 2.7). Determinista, sin LLM."""
from collections.abc import Callable
from datetime import datetime

from ..core.reloj import ahora_ba
from .nodos import ESTADOS_OK, documentacion_ok, seguridad_ok

ETIQUETA_AVISOS = {
    "news2_parcial": "NEWS2 calculado con datos incompletos (el puntaje es un mínimo)",
    "news2_no_aplicable": "NEWS2 no aplica (menor de 16 años)",
    "morse_no_evaluable": "Escala de Morse no evaluable (sin valoración de caídas)",
}
NOMBRE_ESCALA = {"news2": "NEWS2", "morse": "Morse"}
RAMAS = ("seguridad", "documentacion")


def _signos(datos) -> str:
    sv = datos.signos_vitales
    return (f"TA {sv.ta_sistolica}/{sv.ta_diastolica}, FC {sv.fc}, FR {sv.fr}, "
            f"SatO2 {sv.sato2}%, T {sv.temperatura} °C, dolor {sv.dolor}/10")


def entrada_historial(state: dict, momento: datetime) -> dict:
    """Registro de ESTA ejecución. Solo confía en lo que escribió una rama que terminó bien."""
    seg = seguridad_ok(state)
    decision = state.get("decision_humana")
    estados = state.get("estado_nodos") or {}
    mostrar_evolucion = documentacion_ok(state) or decision == "editado"
    return {
        "clave": state.get("idempotency_key"),
        "hora": momento.strftime("%H:%M"),
        "turno": state.get("turno"),
        "decision": decision,
        "signos": _signos(state["datos_estructurados"]),
        "evolucion": state.get("evolucion") if mostrar_evolucion else None,
        "seguridad_disponible": seg,
        "alertas": ([{"tipo": a.tipo_alerta, "severidad": a.severidad,
                      "descripcion": a.descripcion}
                     for a in state.get("alertas_actuales", [])] if seg else []),
        "puntajes": dict(state.get("puntajes_escalas", {})) if seg else {},
        "avisos": list(state.get("avisos_seguridad", [])) if seg else [],
        "ramas_fallidas": [n for n in RAMAS if estados.get(n) not in ESTADOS_OK],
        "tareas": [{"horario": t["horario"], "descripcion": t.get("descripcion", t["tipo"])}
                   for t in state.get("tareas", [])],
    }


def _bloque(i: int, e: dict) -> list[str]:
    estado = {"aprobado": "aprobado", "editado": "editado por la enfermera"}.get(
        e["decision"], str(e["decision"]))
    lineas = [f"[{e['hora']}] Registro {i} ({estado})", f"Signos vitales: {e['signos']}"]

    lineas.append(f"Evolución: {e['evolucion']}" if e["evolucion"] else "Evolución: no disponible.")

    if not e["seguridad_disponible"]:
        lineas.append("Alertas: no disponibles (falló el análisis de seguridad); "
                      "requiere revisión manual.")
    elif e["alertas"]:
        lineas.append("Alertas: " + "; ".join(
            f"{a['tipo']} ({a['severidad']}): {a['descripcion'].rstrip('.')}" for a in e["alertas"]))
    else:
        lineas.append("Alertas: ninguna.")

    if e["puntajes"]:
        lineas.append("Escalas: " + ", ".join(
            f"{NOMBRE_ESCALA.get(k, k)} {v}" for k, v in e["puntajes"].items()))
    for aviso in e["avisos"]:
        lineas.append(f"Aviso: {ETIQUETA_AVISOS.get(aviso, aviso)}.")
    if e["ramas_fallidas"]:
        lineas.append("Registro incompleto: faltan resultados de "
                      + ", ".join(e["ramas_fallidas"]) + ".")
    lineas.append("")
    return lineas


def generar_pase(historial: list[dict]) -> str:
    unicos: dict = {}
    for e in historial:                       # misma clave = mismo registro; gana el último
        unicos[e.get("clave") or id(e)] = e
    registros = list(unicos.values())
    ultimo = registros[-1]

    lineas = [f"PASE DE GUARDIA - turno {ultimo['turno']}",
              f"Registros del turno: {len(registros)}", ""]
    for i, e in enumerate(registros, 1):
        lineas += _bloque(i, e)

    lineas.append("Pendientes al cierre:")
    lineas += ([f"- {t['horario']} {t['descripcion']}" for t in ultimo["tareas"]]
               or ["- ninguno"])
    return "\n".join(lineas)


def crear_nodo_consolidar(ahora: Callable[[], datetime] = ahora_ba):
    def nodo_consolidar(state: dict) -> dict:
        entrada = entrada_historial(state, ahora())
        historial = list(state.get("historial_turno", [])) + [entrada]
        return {
            "historial_turno": [entrada],                 # el reducer lo agrega al acumulado
            "pase_guardia": generar_pase(historial),
            "estado_nodos": {"consolidar": "ok"},
        }

    return nodo_consolidar
