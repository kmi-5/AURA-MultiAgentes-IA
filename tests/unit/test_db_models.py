from backend.app.core.db import Base
from backend.app.models import db_models  # noqa: F401  (registra los modelos en la metadata)

TABLAS_ESPERADAS = {
    "pacientes", "signos_vitales", "medicacion", "alertas_seguridad",
    "tareas", "pases_turno", "usuarios_enfermeria", "auditoria", "valoracion_caidas",
    "idempotencia"
}


def test_las_10_tablas():
    assert set(Base.metadata.tables) == TABLAS_ESPERADAS


def test_alertas_tienen_version_de_reglas():
    assert "version_reglas" in Base.metadata.tables["alertas_seguridad"].c


def test_pases_turno_tiene_clave_de_idempotencia_unica():
    col = Base.metadata.tables["pases_turno"].c.idempotency_key
    assert col.unique is True


def test_tablas_clinicas_referencian_pacientes():
    for nombre in ("signos_vitales", "medicacion", "alertas_seguridad", "tareas", "pases_turno"):
        fks = {fk.column.table.name for fk in Base.metadata.tables[nombre].foreign_keys}
        assert "pacientes" in fks