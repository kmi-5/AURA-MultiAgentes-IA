"""Puntaje de la Escala de Caídas de Morse (Morse, Morse y Tylko, 1989, Can J Aging 8(4):366-377).

Función pura, sin LLM ni base de datos. El corte de riesgo alto NO está acá: es
parametrizable y vive en reglas_seguridad.yaml (regla riesgo_caida).
"""
from collections.abc import Mapping
from dataclasses import dataclass

# ítem -> {valor: puntos}. Los valores coinciden con los CheckConstraint de valoracion_caidas.
TABLA_MORSE: dict[str, dict] = {
    "antecedente_caidas":     {False: 0, True: 25},
    "diagnostico_secundario": {False: 0, True: 15},
    "ayuda_deambular":        {"ninguna_o_asistida": 0,
                               "baston_muletas_andador": 15,
                               "se_apoya_en_muebles": 30},
    "via_iv":                 {False: 0, True: 20},
    "marcha":                 {"normal_o_inmovil": 0, "debil": 10, "alterada": 20},
    "estado_mental":          {"conoce_limites": 0, "olvida_limitaciones": 15},
}

PUNTAJE_MAXIMO = sum(max(opciones.values()) for opciones in TABLA_MORSE.values())   # 125


@dataclass(frozen=True)
class ResultadoMorse:
    evaluable: bool                  # False si no hay valoración de caídas
    puntaje: int | None
    por_item: dict[str, int]


def puntaje_item(item: str, valor) -> int:
    if item not in TABLA_MORSE:
        raise ValueError(f"ítem de Morse desconocido: {item!r}")
    valor = getattr(valor, "value", valor)          # acepta el Enum del schema o un str
    opciones = TABLA_MORSE[item]
    # los ítems booleanos no aceptan 0/1 ni "si": solo bool
    if all(isinstance(k, bool) for k in opciones) and not isinstance(valor, bool):
        raise ValueError(f"{item}: se esperaba un booleano, llegó {valor!r}")
    try:
        return opciones[valor]
    except (KeyError, TypeError):
        raise ValueError(f"valor inválido para {item}: {valor!r}") from None


def calcular_morse(valoracion: Mapping[str, object] | None) -> ResultadoMorse:
    """`valoracion` es un dict con los 6 ítems (para un modelo Pydantic, usar .model_dump())."""
    if valoracion is None:
        return ResultadoMorse(evaluable=False, puntaje=None, por_item={})
    faltan = [i for i in TABLA_MORSE if i not in valoracion]
    if faltan:
        raise ValueError(f"faltan ítems de Morse: {faltan}")
    por_item = {i: puntaje_item(i, valoracion[i]) for i in TABLA_MORSE}
    return ResultadoMorse(evaluable=True, puntaje=sum(por_item.values()), por_item=por_item)
