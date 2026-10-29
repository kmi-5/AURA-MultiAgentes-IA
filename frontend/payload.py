"""Arma y valida el cuerpo de /procesar. Funciones puras (sin Streamlit, sin HTTP).

Los rangos son una AYUDA para detectar errores de tipeo antes de enviar; la autoridad
es la API (`DatosEntrada`). Si la API devuelve 422, sus mensajes mandan.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime

TURNOS = {"manana": "Mañana", "tarde": "Tarde", "noche": "Noche"}

# Plausibilidad fisiológica (NO umbrales clínicos). Espejo de SignosVitales en la API.
RANGOS = {
    "ta_sistolica": (50, 260), "ta_diastolica": (30, 160), "fc": (20, 250), "fr": (4, 60),
    "sato2": (50, 100), "temperatura": (30.0, 43.0), "dolor": (0, 10),
}
ETIQUETAS = {
    "ta_sistolica": "TA sistólica (mmHg)", "ta_diastolica": "TA diastólica (mmHg)",
    "fc": "FC (lpm)", "fr": "FR (rpm)", "sato2": "SatO₂ (%)",
    "temperatura": "Temperatura (°C)", "dolor": "Dolor (0–10)",
}
CONCIENCIA = {"A": "A – Alerta", "C": "C – Confusión nueva", "V": "V – Responde a la voz",
              "P": "P – Responde al dolor", "U": "U – Sin respuesta"}
AYUDA = {"ninguna_o_asistida": "Ninguna / asistida por enfermería / reposo en cama (0)",
         "baston_muletas_andador": "Bastón, muletas o andador (15)",
         "se_apoya_en_muebles": "Se apoya en los muebles (30)"}
MARCHA = {"normal_o_inmovil": "Normal / en cama / inmóvil (0)", "debil": "Débil (10)",
          "alterada": "Alterada (20)"}
ESTADO_MENTAL = {"conoce_limites": "Conoce sus limitaciones (0)",
                 "olvida_limitaciones": "Olvida sus limitaciones (15)"}

MAX_OBS, MAX_DISP, MAX_MED = 500, 10, 20
_HORA = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*$")
_ENTEROS = ("ta_sistolica", "ta_diastolica", "fc", "fr", "sato2", "dolor")


def turno_por_hora(hora: int) -> str:
    if 6 <= hora < 14:
        return "manana"
    return "tarde" if 14 <= hora < 22 else "noche"


def turno_actual() -> str:
    try:
        from zoneinfo import ZoneInfo
        ahora = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires"))
    except Exception:
        ahora = datetime.now()
    return turno_por_hora(ahora.hour)


def fecha_ba():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()
    except Exception:
        return datetime.now().date()


def thread_id_para(paciente_id: int, turno: str, fecha=None) -> str:
    """Espejo de make_thread_id (backend/app/core/checkpointer.py). CONFIRMAR el formato.
    Sirve solo para recuperar un turno pendiente tras recargar el navegador."""
    return f"{paciente_id}:{turno}:{(fecha or fecha_ba()).isoformat()}"


def parsear_lineas(texto: str | None) -> list[str]:
    return [x.strip() for x in (texto or "").splitlines() if x.strip()]


def normalizar_hora(texto: str) -> str | None:
    m = _HORA.match(texto)
    if not m:
        return None
    hh, mm = int(m.group(1)), int(m.group(2))
    return f"{hh:02d}:{mm:02d}" if hh <= 23 and mm <= 59 else None


def parsear_horarios(texto: str | None) -> list[str]:
    """'8:00, 14:00' o una por línea. Los inválidos se conservan tal cual para que validar() los marque."""
    crudos = [x.strip() for x in re.split(r"[,\n;]+", texto or "") if x.strip()]
    return [normalizar_hora(x) or x for x in crudos]


def _num(v, entero: bool):
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    return int(f) if entero and f == int(f) else f


def armar_payload(v: dict) -> dict:
    """`v` = valores planos del formulario. Devuelve el cuerpo con la forma de DatosEntrada."""
    signos = {k: _num(v.get(k), k in _ENTEROS) for k in RANGOS}
    signos["o2_suplementario"] = v.get("o2_suplementario")
    signos["conciencia"] = v.get("conciencia")
    signos["escala_spo2"] = v.get("escala_spo2", 1)
    caidas = v.get("caidas") or {}
    clave_caidas = ("antecedente_caidas", "diagnostico_secundario", "ayuda_deambular",
                    "via_iv", "marcha", "estado_mental")
    return {
        "paciente_id": v.get("paciente_id"),
        "turno": v.get("turno"),
        "signos_vitales": signos,
        "observacion": (v.get("observacion") or "").strip(),
        "dispositivos": parsear_lineas(v.get("dispositivos")),
        "medicacion_programada": parsear_horarios(v.get("medicacion")),
        "valoracion_caidas": {k: caidas.get(k) for k in clave_caidas},
    }


def validar(p: dict) -> dict[str, str]:
    """Errores por campo con la misma notación que los 422: 'signos_vitales.fc'."""
    e: dict[str, str] = {}
    if not p.get("paciente_id"):
        e["paciente_id"] = "Elegí un paciente."
    if p.get("turno") not in TURNOS:
        e["turno"] = "Elegí un turno."
    sv = p.get("signos_vitales", {})
    for campo, (lo, hi) in RANGOS.items():
        val = sv.get(campo)
        if val is None:
            e[f"signos_vitales.{campo}"] = "Obligatorio."
        elif not isinstance(val, (int, float)) or isinstance(val, bool):
            e[f"signos_vitales.{campo}"] = "Ingresá un número."
        elif not lo <= val <= hi:
            e[f"signos_vitales.{campo}"] = f"Fuera de rango plausible ({lo}–{hi}). ¿Error de tipeo?"
    s, d = sv.get("ta_sistolica"), sv.get("ta_diastolica")
    if isinstance(s, (int, float)) and isinstance(d, (int, float)) and s <= d:
        e.setdefault("signos_vitales.ta_sistolica", "La sistólica debe ser mayor que la diastólica.")
    if sv.get("o2_suplementario") is None:
        e["signos_vitales.o2_suplementario"] = "Indicá si recibe oxígeno suplementario."
    if sv.get("conciencia") not in CONCIENCIA:
        e["signos_vitales.conciencia"] = "Elegí el nivel de conciencia."
    if sv.get("escala_spo2") not in (1, 2):
        e["signos_vitales.escala_spo2"] = "Escala 1 o 2."
    if len(p.get("observacion", "")) > MAX_OBS:
        e["observacion"] = f"Máximo {MAX_OBS} caracteres."
    if len(p.get("dispositivos", [])) > MAX_DISP:
        e["dispositivos"] = f"Máximo {MAX_DISP} dispositivos."
    med = p.get("medicacion_programada", [])
    if len(med) > MAX_MED:
        e["medicacion_programada"] = f"Máximo {MAX_MED} horarios."
    malos = [h for h in med if normalizar_hora(h) is None]
    if malos:
        e["medicacion_programada"] = f"Horario inválido: {', '.join(malos)} (formato HH:MM)."
    vc = p.get("valoracion_caidas") or {}
    for campo, opciones in (("ayuda_deambular", AYUDA), ("marcha", MARCHA), ("estado_mental", ESTADO_MENTAL)):
        if vc.get(campo) not in opciones:
            e[f"valoracion_caidas.{campo}"] = "Elegí una opción."
    for campo in ("antecedente_caidas", "diagnostico_secundario", "via_iv"):
        if not isinstance(vc.get(campo), bool):
            e[f"valoracion_caidas.{campo}"] = "Elegí Sí o No."
    return e


def huella(p: dict) -> str:
    """Identifica el contenido del envío: mismo contenido = misma huella (base de la Idempotency-Key)."""
    canon = json.dumps(p, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()


# Casos de demostración (solo dev). Copiados del golden set; cada uno va con el paciente del seed
# que tiene esos mismos datos (Paciente 01/02/03 (Prueba), ids 1/2/3).
CASOS_DEMO = {
    "Estable, sin alertas": dict(
        paciente_id=1,
        ta_sistolica=120, ta_diastolica=80, fc=72, fr=18, sato2=98, temperatura=36.6, dolor=1,
        o2_suplementario=False, conciencia="A", escala_spo2=1,
        observacion="Lúcido, orientado, deambula sin ayuda.", dispositivos="vía periférica MSD",
        medicacion="08:00",
        caidas=dict(antecedente_caidas=False, diagnostico_secundario=False,
                    ayuda_deambular="ninguna_o_asistida", via_iv=True,
                    marcha="normal_o_inmovil", estado_mental="conoce_limites")),
    "Riesgo de caída": dict(
        paciente_id=2,
        ta_sistolica=135, ta_diastolica=85, fc=88, fr=18, sato2=95, temperatura=36.8, dolor=3,
        o2_suplementario=False, conciencia="A", escala_spo2=1,
        observacion="Lúcido, refiere mareos al incorporarse. Deambula con andador.",
        dispositivos="vía periférica MSI", medicacion="06:00\n08:00",
        caidas=dict(antecedente_caidas=False, diagnostico_secundario=True,
                    ayuda_deambular="baston_muletas_andador", via_iv=True,
                    marcha="debil", estado_mental="conoce_limites")),
    "Saturación baja y taquipnea": dict(
        paciente_id=3,
        ta_sistolica=110, ta_diastolica=70, fc=95, fr=24, sato2=85, temperatura=37.0, dolor=2,
        o2_suplementario=True, conciencia="A", escala_spo2=1,
        observacion="Disnea leve al hablar. Cánula nasal a 2 L/min.", dispositivos="cánula nasal",
        medicacion="08:00",
        caidas=dict(antecedente_caidas=False, diagnostico_secundario=False,
                    ayuda_deambular="ninguna_o_asistida", via_iv=False,
                    marcha="normal_o_inmovil", estado_mental="conoce_limites")),
}
