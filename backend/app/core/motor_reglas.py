"""Motor determinista del Agente Seguridad (paso 2.2).

Aplica las reglas versionadas de reglas_seguridad.yaml a los datos del turno.
Función pura: sin LLM, sin base de datos, sin estado. El LLM solo redacta la
descripción de las alertas que este motor dispara: no puede crear ni suprimir ninguna.
"""
import operator
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache

from .morse import ResultadoMorse, calcular_morse
from .news2 import ResultadoNews2, calcular_news2
from .reglas import ConjuntoReglas, ReglaEscala, ReglaUmbral, cargar_reglas

_OPERADORES = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge}


@dataclass(frozen=True)
class AlertaMotor:
    regla_id: str                    # va a alertas_seguridad.tipo_alerta
    descripcion: str                 # descripción base de la regla (el LLM la redacta)
    fuente: str
    severidad: str                   # baja | media | alta, declarada en la regla
    observado: dict[str, object]     # qué dato disparó la alerta (trazabilidad)

@dataclass(frozen=True)
class ResultadoSeguridad:
    version_reglas: str              # va a alertas_seguridad.version_reglas
    alertas: tuple[AlertaMotor, ...]
    news2: ResultadoNews2
    morse: ResultadoMorse
    avisos: tuple[str, ...]          # limitaciones del cálculo, para mostrar en la interfaz

    @property
    def puntajes_escalas(self) -> dict[str, int]:
        """Para TurnoState.puntajes_escalas: omite las escalas que no se pudieron calcular."""
        p: dict[str, int] = {}
        if self.news2.puntaje is not None:
            p["news2"] = self.news2.puntaje
        if self.morse.puntaje is not None:
            p["morse"] = self.morse.puntaje
        return p


@cache
def _reglas_por_defecto() -> ConjuntoReglas:
    return cargar_reglas()


def _en_rango(valor: int, minimo: int | None, maximo: int | None) -> bool:
    return (minimo is None or valor >= minimo) and (maximo is None or valor <= maximo)


def evaluar_seguridad(
    *,
    edad: int,
    signos: Mapping[str, object],
    valoracion_caidas: Mapping[str, object] | None,
    reglas: ConjuntoReglas | None = None,
) -> ResultadoSeguridad:
    reglas = reglas or _reglas_por_defecto()
    escala_spo2 = signos.get("escala_spo2") or 1

    news2 = calcular_news2(
        edad=edad,
        fr=signos.get("fr"),
        sato2=signos.get("sato2"),
        ta_sistolica=signos.get("ta_sistolica"),
        fc=signos.get("fc"),
        temperatura=signos.get("temperatura"),
        o2_suplementario=signos.get("o2_suplementario"),
        conciencia=signos.get("conciencia"),
        escala_spo2=escala_spo2,
    )
    morse = calcular_morse(valoracion_caidas)

    alertas: list[AlertaMotor] = []
    for regla in reglas.reglas:
        if not regla.aplica_a_edad(edad):
            continue

        observado: dict[str, object] | None = None

        if isinstance(regla, ReglaUmbral):
            if regla.aplica_escala_spo2 is not None and regla.aplica_escala_spo2 != escala_spo2:
                continue
            valor = signos.get(regla.parametro)
            if valor is not None and _OPERADORES[regla.operador](valor, regla.valor):
                observado = {regla.parametro: valor}

        elif isinstance(regla, ReglaEscala):
            if regla.escala == "news2":
                if not news2.aplicable:
                    continue
                if regla.criterio == "parametro_rojo":
                    en_3 = [k for k, v in news2.por_parametro.items() if v == 3]
                    if en_3:
                        observado = {"parametros_en_3": en_3}
                elif _en_rango(news2.puntaje, regla.minimo, regla.maximo):
                    observado = {"news2": news2.puntaje, "parcial": news2.parcial}
            else:  # morse
                if morse.evaluable and _en_rango(morse.puntaje, regla.minimo, regla.maximo):
                    observado = {"morse": morse.puntaje}

        if observado is not None:
            alertas.append(AlertaMotor(regla_id=regla.id, descripcion=regla.descripcion,
                                       fuente=regla.fuente, severidad=regla.severidad,
                                       observado=observado))

    avisos: list[str] = []
    if not news2.aplicable:
        avisos.append("news2_no_aplicable")
    elif news2.parcial:
        avisos.append("news2_parcial")
    if not morse.evaluable:
        avisos.append("morse_no_evaluable")

    return ResultadoSeguridad(
        version_reglas=reglas.version,
        alertas=tuple(alertas),
        news2=news2,
        morse=morse,
        avisos=tuple(avisos),
    )
