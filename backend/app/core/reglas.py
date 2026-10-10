"""Carga y validación de las reglas versionadas del Agente Seguridad."""
from pathlib import Path
from typing import Annotated, Literal, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

RUTA_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "reglas_seguridad.yaml"
FUENTE_LOCAL = "convencion_local"


class _ReglaBase(BaseModel):
    # extra="forbid": un typo en el YAML falla al cargar en vez de ignorarse en silencio
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=50)
    descripcion: str = Field(min_length=3)
    fuente: str = Field(min_length=3)
    validada: bool
    severidad: Literal["baja", "media", "alta"] = "media"
    edad_minima: int | None = Field(default=None, ge=0, le=120)   # None = sin restricción

    def aplica_a_edad(self, edad: int) -> bool:
        return self.edad_minima is None or edad >= self.edad_minima

    @model_validator(mode="after")
    def _local_no_puede_estar_validada(self):
        if self.validada and self.fuente == FUENTE_LOCAL:
            raise ValueError(f"{self.id}: una regla local sin fuente no puede estar validada")
        return self


class ReglaUmbral(_ReglaBase):
    tipo: Literal["umbral"]
    parametro: Literal["ta_sistolica", "ta_diastolica", "fc", "fr",
                       "sato2", "temperatura", "dolor"]
    operador: Literal["<", "<=", ">", ">="]
    valor: float
    aplica_escala_spo2: Literal[1, 2] | None = None


class ReglaEscala(_ReglaBase):
    tipo: Literal["escala"]
    escala: Literal["news2", "morse"]
    criterio: Literal["total", "parametro_rojo"]
    minimo: int | None = Field(default=None, ge=0)
    maximo: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _coherente(self):
        if self.criterio == "parametro_rojo":
            if self.escala != "news2":
                raise ValueError(f"{self.id}: 'parametro_rojo' solo existe en NEWS2")
            if self.minimo is not None or self.maximo is not None:
                raise ValueError(f"{self.id}: 'parametro_rojo' no lleva minimo ni maximo")
        else:
            if self.minimo is None:
                raise ValueError(f"{self.id}: el criterio 'total' requiere 'minimo'")
            if self.maximo is not None and self.maximo < self.minimo:
                raise ValueError(f"{self.id}: maximo menor que minimo")
        return self


Regla = Annotated[Union[ReglaUmbral, ReglaEscala], Field(discriminator="tipo")]


class ConjuntoReglas(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    reglas: list[Regla] = Field(min_length=1)

    @model_validator(mode="after")
    def _ids_unicos(self):
        ids = [r.id for r in self.reglas]
        repetidos = {i for i in ids if ids.count(i) > 1}
        if repetidos:
            raise ValueError(f"ids de regla repetidos: {sorted(repetidos)}")
        return self

    def por_id(self, id_: str) -> Regla:
        return next(r for r in self.reglas if r.id == id_)


def cargar_reglas(ruta: Path | None = None) -> ConjuntoReglas:
    with open(ruta or RUTA_DEFAULT, encoding="utf-8") as f:
        return ConjuntoReglas.model_validate(yaml.safe_load(f))
