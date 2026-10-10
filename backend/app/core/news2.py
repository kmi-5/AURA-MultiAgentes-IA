"""Puntaje NEWS2 (Royal College of Physicians, 2017). Funciones puras, sin LLM ni base de datos.

Los umbrales NO se modifican. Cualquier cambio requiere revisar la tabla oficial.
No aplica a menores de 16 años (ni a embarazadas: limitación documentada del sistema).
"""
from dataclasses import dataclass

EDAD_MINIMA_NEWS2 = 16
NIVELES_CONCIENCIA = ("A", "C", "V", "P", "U")


def puntaje_fr(fr: float) -> int:
    if fr <= 8:
        return 3
    if fr <= 11:
        return 1
    if fr <= 20:
        return 0
    if fr <= 24:
        return 2
    return 3


def puntaje_spo2_escala1(sato2: float) -> int:
    if sato2 <= 91:
        return 3
    if sato2 <= 93:
        return 2
    if sato2 <= 95:
        return 1
    return 0


def puntaje_spo2_escala2(sato2: float, o2_suplementario: bool | None) -> int | None:
    """Escala 2 (objetivo 88-92 %, p. ej. EPOC hipercápnico).

    Desde 93 % el puntaje depende de si hay O2 suplementario. Si ese dato falta,
    devuelve None (no se puede puntuar) en vez de asumir aire ambiente.
    """
    if sato2 <= 83:
        return 3
    if sato2 <= 85:
        return 2
    if sato2 <= 87:
        return 1
    if sato2 <= 92:
        return 0
    if o2_suplementario is None:
        return None
    if not o2_suplementario:
        return 0
    if sato2 <= 94:
        return 1
    if sato2 <= 96:
        return 2
    return 3


def puntaje_o2(o2_suplementario: bool) -> int:
    return 2 if o2_suplementario else 0


def puntaje_tas(ta_sistolica: float) -> int:
    if ta_sistolica <= 90:
        return 3
    if ta_sistolica <= 100:
        return 2
    if ta_sistolica <= 110:
        return 1
    if ta_sistolica <= 219:
        return 0
    return 3


def puntaje_fc(fc: float) -> int:
    if fc <= 40:
        return 3
    if fc <= 50:
        return 1
    if fc <= 90:
        return 0
    if fc <= 110:
        return 1
    if fc <= 130:
        return 2
    return 3


def puntaje_conciencia(nivel) -> int:
    """ACVPU: Alerta = 0; Confusión nueva, Voz, Dolor o Inconsciente = 3."""
    nivel = getattr(nivel, "value", nivel)       # acepta el Enum del schema o un str
    if nivel not in NIVELES_CONCIENCIA:
        raise ValueError(f"nivel de conciencia inválido: {nivel!r}")
    return 0 if nivel == "A" else 3


def puntaje_temperatura(temperatura: float) -> int:
    if temperatura <= 35.0:
        return 3
    if temperatura <= 36.0:
        return 1
    if temperatura <= 38.0:
        return 0
    if temperatura <= 39.0:
        return 1
    return 2


@dataclass(frozen=True)
class ResultadoNews2:
    aplicable: bool                      # False si NEWS2 no corresponde (menor de 16)
    puntaje: int | None                  # None si no es aplicable
    parcial: bool                        # True si faltan datos: el puntaje es una cota inferior
    por_parametro: dict[str, int]        # solo los parámetros que se pudieron puntuar
    faltantes: tuple[str, ...]
    rojo_unico: bool                     # algún parámetro individual puntúa 3


def calcular_news2(
    *,
    edad: int,
    fr: float | None,
    sato2: float | None,
    ta_sistolica: float | None,
    fc: float | None,
    temperatura: float | None,
    o2_suplementario: bool | None = None,
    conciencia=None,
    escala_spo2: int | None = None,
) -> ResultadoNews2:
    if edad < EDAD_MINIMA_NEWS2:
        return ResultadoNews2(aplicable=False, puntaje=None, parcial=False,
                              por_parametro={}, faltantes=(), rojo_unico=False)

    escala = 1 if escala_spo2 is None else escala_spo2
    if escala not in (1, 2):
        raise ValueError(f"escala_spo2 inválida: {escala_spo2!r}")

    if sato2 is None:
        spo2 = None
    elif escala == 1:
        spo2 = puntaje_spo2_escala1(sato2)
    else:
        spo2 = puntaje_spo2_escala2(sato2, o2_suplementario)

    puntos = {
        "fr": None if fr is None else puntaje_fr(fr),
        "sato2": spo2,
        "o2_suplementario": None if o2_suplementario is None else puntaje_o2(o2_suplementario),
        "ta_sistolica": None if ta_sistolica is None else puntaje_tas(ta_sistolica),
        "fc": None if fc is None else puntaje_fc(fc),
        "conciencia": None if conciencia is None else puntaje_conciencia(conciencia),
        "temperatura": None if temperatura is None else puntaje_temperatura(temperatura),
    }
    por_parametro = {k: v for k, v in puntos.items() if v is not None}
    faltantes = tuple(k for k, v in puntos.items() if v is None)

    return ResultadoNews2(
        aplicable=True,
        puntaje=sum(por_parametro.values()),
        parcial=bool(faltantes),
        por_parametro=por_parametro,
        faltantes=faltantes,
        rojo_unico=any(v == 3 for v in por_parametro.values()),
    )
