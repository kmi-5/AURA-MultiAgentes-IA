from datetime import datetime, time

from sqlalchemy import (CheckConstraint, DateTime, ForeignKey, String, Text, JSON, Time, func, text)
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


class Paciente(Base):
    __tablename__ = "pacientes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    edad: Mapped[int]
    habitacion: Mapped[str] = mapped_column(String(10))

    __table_args__ = (CheckConstraint("edad BETWEEN 0 AND 120", name="ck_pacientes_edad"),)


class UsuarioEnfermeria(Base):
    __tablename__ = "usuarios_enfermeria"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    username: Mapped[str] = mapped_column(String(50), unique=True)
    rol: Mapped[str] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(200))   # nunca la contraseña en claro

    __table_args__ = (
        CheckConstraint("rol IN ('enfermeria','supervision','auditoria')", name="ck_usuarios_rol"),
    )


class SignosVitalesRow(Base):
    __tablename__ = "signos_vitales"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id", ondelete="CASCADE"), index=True)
    ta_sistolica: Mapped[int]
    ta_diastolica: Mapped[int]
    fc: Mapped[int]
    fr: Mapped[int]
    sato2: Mapped[int]
    temperatura: Mapped[float]
    dolor: Mapped[int]
    o2_suplementario: Mapped[bool | None]
    conciencia: Mapped[str | None] = mapped_column(String(1))      # ACVPU
    escala_spo2: Mapped[int] = mapped_column(server_default=text("1"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (CheckConstraint("dolor BETWEEN 0 AND 10", name="ck_signos_dolor"),)


class ValoracionCaidasRow(Base):
    """Ítems de la Morse Fall Scale. El puntaje lo calcula el motor de reglas."""
    __tablename__ = "valoracion_caidas"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id", ondelete="CASCADE"), index=True)
    turno: Mapped[str] = mapped_column(String(10))
    antecedente_caidas: Mapped[bool]
    diagnostico_secundario: Mapped[bool]
    ayuda_deambular: Mapped[str] = mapped_column(String(30))
    via_iv: Mapped[bool]
    marcha: Mapped[str] = mapped_column(String(20))
    estado_mental: Mapped[str] = mapped_column(String(25))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "ayuda_deambular IN ('ninguna_o_asistida','baston_muletas_andador','se_apoya_en_muebles')",
            name="ck_caidas_ayuda"),
        CheckConstraint("marcha IN ('normal_o_inmovil','debil','alterada')", name="ck_caidas_marcha"),
        CheckConstraint("estado_mental IN ('conoce_limites','olvida_limitaciones')",
                        name="ck_caidas_estado_mental"),
    )


class Medicacion(Base):
    __tablename__ = "medicacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id", ondelete="CASCADE"), index=True)
    medicamento: Mapped[str] = mapped_column(String(120))
    dosis: Mapped[str] = mapped_column(String(50))
    frecuencia: Mapped[str] = mapped_column(String(30))
    horario_programado: Mapped[time] = mapped_column(Time)
    estado: Mapped[str] = mapped_column(String(15), default="pendiente")
    timestamp_ejecucion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("estado IN ('pendiente','completada')", name="ck_medicacion_estado"),
    )


class AlertaSeguridad(Base):
    __tablename__ = "alertas_seguridad"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id", ondelete="CASCADE"), index=True)
    tipo_alerta: Mapped[str] = mapped_column(String(50))
    descripcion: Mapped[str] = mapped_column(Text)
    estado_revision: Mapped[str] = mapped_column(String(15), default="pendiente")
    version_reglas: Mapped[str] = mapped_column(String(20))     # trazabilidad (sección 4.1)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("estado_revision IN ('pendiente','revisada','descartada')",
                        name="ck_alertas_estado"),
    )


class Tarea(Base):
    __tablename__ = "tareas"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(30))               # medicacion | control | revision
    horario: Mapped[time] = mapped_column(Time)
    estado: Mapped[str] = mapped_column(String(15), default="pendiente")
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios_enfermeria.id"))

    __table_args__ = (
        CheckConstraint("estado IN ('pendiente','completada')", name="ck_tareas_estado"),
    )


class PaseTurno(Base):
    __tablename__ = "pases_turno"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id", ondelete="CASCADE"), index=True)
    turno: Mapped[str] = mapped_column(String(10))
    contenido_consolidado: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)   # anti doble click (12.1)
    incompleto: Mapped[bool] = mapped_column(default=False)
    timestamp_generacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Auditoria(Base):
    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios_enfermeria.id"), index=True, nullable=True)
    detalle: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tarea: Mapped[str] = mapped_column(String(80))
    estado: Mapped[str] = mapped_column(String(20))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Idempotencia(Base):
    __tablename__ = "idempotencia"

    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios_enfermeria.id"), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(64), primary_key=True)
    clave: Mapped[str] = mapped_column(String(128), primary_key=True)
    huella: Mapped[str] = mapped_column(String(64))
    estado: Mapped[str] = mapped_column(String(16))          # en_proceso | completada
    status_code: Mapped[int | None] = mapped_column(nullable=True)
    respuesta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))