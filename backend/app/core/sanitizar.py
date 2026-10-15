"""Sanitización del texto libre que llega a los agentes LLM (paso 2.3c).

Capa de defensa en el límite de la API. NO es la defensa principal: las alertas las decide
un motor determinista, la salida de los LLM se valida contra schema y la enfermera aprueba
antes de guardar. Esto reduce la superficie y deja registro de los intentos.
"""
import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

MAX_OBSERVACION = 500
MAX_DISPOSITIVO = 60

_RE_DISPOSITIVO = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9][A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9 .,/()%+:\-]*$")
_RE_HORA = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")

# Se evalúan sobre el texto en minúsculas y sin tildes. Piden verbo + objeto + calificador
# para no bloquear frases clínicas ("paciente ignora instrucciones de dieta").
_PATRONES: dict[str, re.Pattern] = {
    "ignorar_instrucciones": re.compile(
        r"\b(?:ignor|olvid|descart|omit)\w*\b.{0,30}\b(?:instruccion|regla|prompt|orden|restriccion)\w*\b"
        r".{0,30}\b(?:anterior|previ|arriba|sistema)\w*"
        r"|\b(?:ignore|disregard|forget)\b.{0,30}\b(?:instruction|rule|prompt|command)s?\b"
    ),
    "reasignar_rol": re.compile(
        r"\b(?:actua|actuas|comportate)\s+como\s+(?:un|una|el|la)\s+"
        r"(?:asistente|ia|modelo|sistema|medico|doctor|enfermer\w+|agente|bot|experto)\b"
        r"|\b(?:ahora|desde ahora)\s+(?:eres|sos|vas a ser)\b"
        r"|\b(?:act as|pretend to be|you are now)\b"
    ),
    "mencionar_sistema": re.compile(
        r"\b(?:system prompt|prompt del sistema|mensaje del sistema|instrucciones del sistema"
        r"|developer message|jailbreak)\b"
    ),
    "suprimir_alertas": re.compile(
        r"\b(?:no\s+(?:generes|crees|emitas|muestres|reportes|incluyas|generar|crear|emitir|mostrar)"
        r"|suprim\w*|elimin\w*|borr\w*|omit\w*)\b.{0,20}\balerta\w*"
    ),
    "formato_salida": re.compile(
        r"\b(?:responde|devuelve|retorna|respond|reply|output)\w*\b.{0,15}\b(?:json|con la palabra|only with)\b"
    ),
    "delimitadores": re.compile(
        r"```|<\||\|>|\[/?inst\]|</?\s*(?:system|assistant|user|dato_no_confiable)\b"
    ),
}


class TextoNoPermitido(ValueError):
    """El texto tiene forma de instrucción al sistema o un formato no admitido."""


def normalizar_texto(texto: str) -> str:
    t = unicodedata.normalize("NFKC", texto).replace("\u2028", "\n").replace("\u2029", "\n")
    # fuera caracteres de control (Cc) e invisibles/bidireccionales (Cf); se conserva \n
    t = "".join(ch for ch in t
                if ch in "\n\t" or unicodedata.category(ch) not in ("Cc", "Cf"))
    lineas = [re.sub(r" {2,}", " ", linea.replace("\t", " ")).strip() for linea in t.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lineas)).strip()


def _forma_comparacion(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", t)


def detectar_instrucciones(texto: str) -> list[str]:
    """Ids de los patrones que coinciden (lista vacía si el texto está limpio)."""
    forma = _forma_comparacion(texto)
    return [nombre for nombre, patron in _PATRONES.items() if patron.search(forma)]


def sanitizar_observacion(texto: str) -> str:
    limpio = normalizar_texto(texto)
    if len(limpio) > MAX_OBSERVACION:
        raise ValueError(f"La observación supera los {MAX_OBSERVACION} caracteres")
    ids = detectar_instrucciones(limpio)
    if ids:
        logger.warning("Observación bloqueada por patrones de instrucción: %s", ids)
        raise TextoNoPermitido(
            "La observación contiene texto con forma de instrucción al sistema. "
            "Reescribila describiendo solo lo observado en el paciente."
        )
    return limpio


def sanitizar_dispositivo(texto: str) -> str:
    limpio = normalizar_texto(texto)
    if not limpio:
        return ""
    if len(limpio) > MAX_DISPOSITIVO or not _RE_DISPOSITIVO.match(limpio):
        raise TextoNoPermitido(f"Dispositivo con formato no permitido: {texto[:30]!r}")
    ids = detectar_instrucciones(limpio)
    if ids:
        logger.warning("Dispositivo bloqueado por patrones de instrucción: %s", ids)
        raise TextoNoPermitido("Dispositivo con formato no permitido")
    return limpio


def sanitizar_dispositivos(lista: list[str]) -> list[str]:
    return [d for d in (sanitizar_dispositivo(x) for x in lista) if d]


def validar_hora(texto: str) -> str:
    limpio = normalizar_texto(texto)
    if not _RE_HORA.match(limpio):
        raise ValueError(f"Horario inválido (se espera HH:MM): {texto[:20]!r}")
    return limpio


def delimitar_dato_no_confiable(texto: str) -> str:
    """Envuelve texto del paciente para los prompts de los agentes (paso 2.4).

    Elimina del interior cualquier etiqueta igual, para que no pueda cerrar el bloque.
    """
    interior = re.sub(r"</?\s*dato_no_confiable[^>]*>?", "", texto, flags=re.IGNORECASE)
    return f"<dato_no_confiable>\n{interior}\n</dato_no_confiable>"
