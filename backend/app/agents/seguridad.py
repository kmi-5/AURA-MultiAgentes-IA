"""Nodo Seguridad del grafo (paso 2.3).

El motor determinista (core/motor_reglas.py) decide QUÉ alertas existen. El LLM, si se
inyecta un `redactor`, solo puede reemplazar el TEXTO de la descripción: no crea ni
suprime alertas, y cualquier falla del redactor cae en la descripción determinista.
La edad sale de la tabla pacientes (única fuente de verdad), no del payload.
"""
import time
import logging
from collections.abc import Callable
from sqlalchemy import select
from ..core.db import SessionLocal
from ..core.motor_reglas import AlertaMotor, evaluar_seguridad
from ..models.db_models import Paciente
from ..models.schemas import Alerta
from ..models.state import TurnoState

logger = logging.getLogger(__name__)

MAX_DESCRIPCION = 500


def edad_desde_db(paciente_id: int) -> int | None:
    with SessionLocal() as s:
        return s.scalar(select(Paciente.edad).where(Paciente.id == paciente_id))


def _detalle(observado: dict) -> str:
    partes = []
    for clave, valor in observado.items():
        if isinstance(valor, (list, tuple)):
            valor = "/".join(str(x) for x in valor)
        partes.append(f"{clave}={valor}")
    return ", ".join(partes)


def descripcion_base(alerta: AlertaMotor) -> str:
    """Texto determinista: descripción de la regla + el dato que la disparó."""
    return f"{alerta.descripcion} ({_detalle(alerta.observado)})"


def _descripcion(alerta: AlertaMotor,
                 redactor: Callable[[AlertaMotor], str] | None) -> tuple[str, bool]:
    """Devuelve (texto, el_redactor_fallo). Un fallo corta el uso del LLM en el resto del turno."""
    base = descripcion_base(alerta)
    if redactor is None:
        return base, False
    try:
        texto = redactor(alerta)
    except Exception:
        logger.warning("El redactor falló para %s; se usa la descripción base", alerta.regla_id)
        return base, True
    if not isinstance(texto, str) or not texto.strip() or len(texto) > MAX_DESCRIPCION:
        logger.warning("El redactor devolvió un texto inválido para %s", alerta.regla_id)
        return base, False
    return texto.strip(), False


def crear_nodo_seguridad(
    obtener_edad: Callable[[int], int | None] = edad_desde_db,
    redactor: Callable[[AlertaMotor], str] | None = None,
    presupuesto_redaccion_s: float = 20.0,
    reloj: Callable[[], float] = time.monotonic,
):
    def nodo_seguridad(state: TurnoState) -> dict:
        datos = state["datos_estructurados"]
        paciente_id = state["paciente_id"]

        edad = obtener_edad(paciente_id)
        if edad is None:
            return {
                "errores": [f"seguridad: paciente {paciente_id} no encontrado"],
                "estado_nodos": {"seguridad": "error"},
            }

        resultado = evaluar_seguridad(
            edad=edad,
            signos=datos.signos_vitales.model_dump(),
            valoracion_caidas=(datos.valoracion_caidas.model_dump()
                               if datos.valoracion_caidas else None),
        )

        inicio = reloj()
        llm_disponible = True
        alertas = []
        for a in resultado.alertas:
            # El LLM tiene un presupuesto de tiempo y un corte de circuito: si una redacción falla
            # (servicio caído), el resto de las alertas usa el texto determinista sin volver a llamarlo.
            usar_llm = (llm_disponible and redactor is not None
                        and (reloj() - inicio) < presupuesto_redaccion_s)
            descripcion, fallo = _descripcion(a, redactor if usar_llm else None)
            if fallo:
                llm_disponible = False
            alertas.append(Alerta(
                tipo_alerta=a.regla_id,
                descripcion=descripcion,
                version_reglas=resultado.version_reglas,
                severidad=a.severidad,
            ))
        return {
            "alertas": alertas,
            "alertas_actuales": alertas,
            "puntajes_escalas": resultado.puntajes_escalas,
            "avisos_seguridad": list(resultado.avisos),
            "estado_nodos": {"seguridad": "ok"},
        }

    return nodo_seguridad