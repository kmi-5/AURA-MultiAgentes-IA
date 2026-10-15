# modelos

from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from ..core import sanitizar as san

class NivelConciencia(str, Enum):
    """Escala ACVPU (NEWS2). C = confusión NUEVA."""
    ALERTA = "A"
    CONFUSION = "C"
    RESPONDE_VOZ = "V"
    RESPONDE_DOLOR = "P"
    SIN_RESPUESTA = "U"


class AyudaDeambular(str, Enum):
    NINGUNA_O_ASISTIDA = "ninguna_o_asistida"       # 0 (incluye reposo en cama)
    BASTON_MULETAS_ANDADOR = "baston_muletas_andador"  # 15
    SE_APOYA_EN_MUEBLES = "se_apoya_en_muebles"      # 30


class Marcha(str, Enum):
    NORMAL_O_INMOVIL = "normal_o_inmovil"  # 0
    DEBIL = "debil"                        # 10
    ALTERADA = "alterada"                  # 20


class EstadoMental(str, Enum):
    CONOCE_LIMITES = "conoce_limites"              # 0
    OLVIDA_LIMITACIONES = "olvida_limitaciones"    # 15


class ValoracionCaidas(BaseModel):
    """Los 6 ítems de la Morse Fall Scale. El puntaje lo calcula el motor, no el usuario."""
    antecedente_caidas: bool = Field(
        ..., description="Caída en esta internación o en los últimos 3 meses"
    )
    diagnostico_secundario: bool = Field(
        ..., description="Más de un diagnóstico médico en la historia clínica"
    )
    ayuda_deambular: AyudaDeambular
    via_iv: bool = Field(..., description="Vía IV o heparinizada")
    marcha: Marcha
    estado_mental: EstadoMental


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
    o2_suplementario: Optional[bool] = Field(
        default=None, description="¿Recibe oxígeno suplementario? None = no informado"
    )
    conciencia: Optional[NivelConciencia] = Field(
        default=None, description="ACVPU. None = no informado"
    )
    escala_spo2: Literal[1, 2] = Field(
        default=1, description="Escala 2 solo por indicación de un clínico (EPOC hipercápnico)"
    )

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
    valoracion_caidas: Optional[ValoracionCaidas] = None

    @field_validator("observacion")
    @classmethod
    def sanitizar_observacion(cls, v: str) -> str:
        return san.sanitizar_observacion(v)

    @field_validator("dispositivos")
    @classmethod
    def sanitizar_dispositivos(cls, v: list[str]) -> list[str]:
        return san.sanitizar_dispositivos(v)

    @field_validator("medicacion_programada")
    @classmethod
    def validar_horas(cls, v: list[str]) -> list[str]:
        return [san.validar_hora(h) for h in v]

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
    paciente_id: int
    turno: Literal["manana", "tarde", "noche"]
    edad: Optional[int] = Field(default=None, ge=0, le=120)  
    signos_vitales: SignosVitales
    observacion: str = ""
    dispositivos: list[str] = Field(default_factory=list)
    medicacion_programada: list[str] = Field(default_factory=list)
    valoracion_caidas: Optional[ValoracionCaidas] = None


class Alerta(BaseModel):
    """Salida del Agente Seguridad. Alerta = 'requiere revisión', nunca diagnóstico."""
    tipo_alerta: str
    descripcion: str
    version_reglas: str
    severidad: Literal["baja", "media", "alta"] = "media"