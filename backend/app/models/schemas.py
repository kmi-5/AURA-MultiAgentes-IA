# modelos

from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class SignosVitales(BaseModel):
    """Rangos = límites de plausibilidad fisiológica (detectar errores de tipeo),
    NO umbrales clínicos. Los umbrales de alerta los define el Agente Seguridad."""
    ta_sistolica: int = Field(ge=50, le=260)
    ta_diastolica: int = Field(ge=30, le=160)
    fc: int = Field(ge=20, le=250)
    fr: int = Field(ge=4, le=60)
    sato2: int = Field(ge=50, le=100)
    temperatura: float = Field(ge=30.0, le=43.0)
    dolor: int = Field(ge=0, le=10)

    @model_validator(mode="after")
    def sistolica_mayor_que_diastolica(self):
        if self.ta_sistolica <= self.ta_diastolica:
            raise ValueError("La TA sistólica debe ser mayor que la diastólica")
        return self


class DatosEntrada(BaseModel):
    """Payload que envía Streamlit al presionar 'Procesar turno'."""
    paciente_id: int = Field(gt=0)
    turno: Literal["manana", "tarde", "noche"]
    signos_vitales: SignosVitales
    observacion: str = Field(default="", max_length=500)   # texto libre: acotado
    dispositivos: list[str] = Field(default_factory=list, max_length=10)
    medicacion_programada: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("observacion")
    @classmethod
    def limpiar_observacion(cls, v: str) -> str:
        # Sanitización mínima: sin caracteres de control y espacios normalizados.
        # El filtrado de instrucciones embebidas (prompt injection) va en Fase 2.
        v = "".join(ch for ch in v if ch.isprintable() or ch in "\n ")
        return " ".join(v.split())

    @field_validator("medicacion_programada")
    @classmethod
    def validar_horarios(cls, v: list[str]) -> list[str]:
        for h in v:
            try:
                hh, mm = h.split(":")
                assert 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59
            except Exception:
                raise ValueError(f"Horario inválido: '{h}' (formato HH:MM)")
        return v


class DatosEstructurados(BaseModel):
    """Salida del Agente Enfermería: única fuente de verdad para los demás agentes."""
    paciente_id: int
    turno: Literal["manana", "tarde", "noche"]
    signos_vitales: SignosVitales
    observacion: str = ""
    dispositivos: list[str] = Field(default_factory=list)
    medicacion_programada: list[str] = Field(default_factory=list)


class Alerta(BaseModel):
    """Salida del Agente Seguridad. Alerta = 'requiere revisión', nunca diagnóstico."""
    tipo_alerta: str
    descripcion: str
    version_reglas: str
    severidad: Literal["baja", "media", "alta"] = "media"