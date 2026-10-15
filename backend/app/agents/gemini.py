"""Adaptador a Gemini vía LangChain. Devuelve una función invocar(prompt) -> str."""
from collections.abc import Callable


def _texto(contenido) -> str:
    """El contenido de la respuesta puede ser un str o una lista de partes."""
    if isinstance(contenido, str):
        return contenido
    partes = []
    for p in contenido:
        if isinstance(p, str):
            partes.append(p)
        elif isinstance(p, dict) and p.get("type") == "text":
            partes.append(p.get("text", ""))
    return "".join(partes)


def crear_invocador_gemini(*, modelo: str, api_key: str, timeout_s: float = 30.0
                           ) -> Callable[[str], str]:
    from langchain_google_genai import ChatGoogleGenerativeAI   # import diferido

    llm = ChatGoogleGenerativeAI(
        model=modelo,
        google_api_key=api_key,
        temperature=0,
        timeout=timeout_s,
        max_retries=0,        # los reintentos con backoff los maneja crear_redactor
    )

    def invocar(prompt: str) -> str:
        return _texto(llm.invoke(prompt).content)

    return invocar
