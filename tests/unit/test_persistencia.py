from datetime import datetime

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.db import Base
from backend.app.core.reglas import cargar_reglas
from backend.app.data.casos_prueba import CASOS
from backend.app.graph import persistencia as modulo
from backend.app.graph.persistencia import crear_nodo_persistencia
from backend.app.models.db_models import (
    AlertaSeguridad, Auditoria, Paciente, PaseTurno, SignosVitalesRow, Tarea,
    UsuarioEnfermeria, ValoracionCaidasRow,
)

MODELOS = (PaseTurno, SignosVitalesRow, ValoracionCaidasRow, AlertaSeguridad, Tarea, Auditoria)
CASO_ALERTAS = "hipertermia_taquicardia_y_taquipnea"          # 5 alertas, 1 medicación


@pytest.fixture
def fabrica():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    f = sessionmaker(engine, expire_on_commit=False)
    with f.begin() as s:
        s.add(Paciente(nombre="Paciente 1", edad=60, habitacion="101"))
        s.add(UsuarioEnfermeria(nombre="Enfermera", username="enf", rol="enfermeria",
                                password_hash="x"))
    yield f
    engine.dispose()


def _caso(escenario):
    return next(c for c in CASOS if c["escenario"] == escenario)


def _nodo(fabrica):
    return crear_nodo_persistencia(session_factory=fabrica, ahora=lambda: datetime(2026, 10, 16, 9, 30))


def _n(fabrica, modelo):
    with fabrica() as s:
        return s.scalar(select(func.count()).select_from(modelo))


def test_aprobar_guarda_todos_los_registros_del_turno(fabrica, armar_estado):
    caso = _caso(CASO_ALERTAS)
    out = _nodo(fabrica)(armar_estado(caso))

    assert out["estado_nodos"] == {"persistencia": "ok"}
    assert _n(fabrica, PaseTurno) == 1
    assert _n(fabrica, SignosVitalesRow) == 1
    assert _n(fabrica, ValoracionCaidasRow) == 1
    assert _n(fabrica, AlertaSeguridad) == len(caso["alertas_esperadas"])
    assert _n(fabrica, Tarea) == len(caso["medicacion"]) + 1 + 1     # medicación + control + revisión
    assert _n(fabrica, Auditoria) == 1


def test_el_pase_y_las_alertas_se_guardan_con_su_trazabilidad(fabrica, armar_estado):
    caso = _caso(CASO_ALERTAS)
    _nodo(fabrica)(armar_estado(caso))
    with fabrica() as s:
        pase = s.scalars(select(PaseTurno)).one()
        alertas = s.scalars(select(AlertaSeguridad)).all()

    assert pase.contenido_consolidado == "Pase de prueba." and pase.incompleto is False
    assert pase.idempotency_key == "clave-1" and pase.turno == "manana"
    assert {a.tipo_alerta for a in alertas} == caso["alertas_esperadas"]
    assert {a.version_reglas for a in alertas} == {cargar_reglas().version}
    assert {a.estado_revision for a in alertas} == {"pendiente"}


@pytest.mark.parametrize("escenario, esperadas", [(CASO_ALERTAS, 1), ("estable_sin_alertas", 0)])
def test_la_tarea_de_revision_solo_existe_si_el_turno_la_requiere(
        fabrica, armar_estado, escenario, esperadas):
    _nodo(fabrica)(armar_estado(_caso(escenario)))
    with fabrica() as s:
        n = s.scalar(select(func.count()).select_from(Tarea).where(Tarea.tipo == "revision"))
    assert n == esperadas


def test_las_tareas_quedan_a_cargo_del_usuario_que_proceso(fabrica, armar_estado):
    _nodo(fabrica)(armar_estado(_caso(CASO_ALERTAS)))
    with fabrica() as s:
        assert {t.responsable_id for t in s.scalars(select(Tarea))} == {1}


def test_reenviar_el_mismo_turno_no_duplica_registros(fabrica, armar_estado):
    caso, nodo = _caso(CASO_ALERTAS), _nodo(fabrica)
    nodo(armar_estado(caso))
    antes = {m: _n(fabrica, m) for m in MODELOS}

    out = nodo(armar_estado(caso))

    assert out["estado_nodos"] == {"persistencia": "ya_guardado"}
    assert {m: _n(fabrica, m) for m in MODELOS} == antes


def test_una_clave_distinta_es_un_registro_nuevo(fabrica, armar_estado):
    caso, nodo = _caso(CASO_ALERTAS), _nodo(fabrica)
    nodo(armar_estado(caso))
    nodo(armar_estado(caso, idempotency_key="clave-2"))
    assert _n(fabrica, PaseTurno) == 2


def test_descartar_solo_deja_la_auditoria(fabrica, armar_estado):
    _nodo(fabrica)(armar_estado(_caso(CASO_ALERTAS), decision="descartado"))

    assert _n(fabrica, Auditoria) == 1
    assert all(_n(fabrica, m) == 0 for m in MODELOS if m is not Auditoria)
    with fabrica() as s:
        assert s.scalars(select(Auditoria)).one().tarea == "turno_descartado"


@pytest.mark.parametrize("decision, tarea", [("aprobado", "turno_aprobado"),
                                             ("editado", "turno_editado")])
def test_la_auditoria_registra_la_decision(fabrica, armar_estado, decision, tarea):
    _nodo(fabrica)(armar_estado(_caso(CASO_ALERTAS), decision=decision))
    with fabrica() as s:
        fila = s.scalars(select(Auditoria)).one()
    assert (fila.tarea, fila.estado, fila.usuario_id) == (tarea, "ok", 1)


def test_un_turno_incompleto_se_marca_en_el_pase_y_en_la_auditoria(fabrica, armar_estado):
    _nodo(fabrica)(armar_estado(_caso(CASO_ALERTAS), turno_incompleto=True))
    with fabrica() as s:
        assert s.scalars(select(PaseTurno)).one().incompleto is True
        assert s.scalars(select(Auditoria)).one().estado == "incompleto"


def test_si_seguridad_fallo_no_se_guardan_alertas(fabrica, armar_estado):
    estado = armar_estado(_caso(CASO_ALERTAS),
                          estado_nodos={"enfermeria": "ok", "seguridad": "timeout",
                                        "documentacion": "ok"})
    _nodo(fabrica)(estado)
    assert _n(fabrica, AlertaSeguridad) == 0
    assert _n(fabrica, SignosVitalesRow) == 1


def test_si_algo_falla_no_queda_nada_a_medias(fabrica, armar_estado):
    estado = armar_estado(_caso(CASO_ALERTAS),
                          tareas=[{"tipo": "medicacion", "horario": "99:99", "estado": "pendiente"}])
    with pytest.raises(ValueError):
        _nodo(fabrica)(estado)
    assert all(_n(fabrica, m) == 0 for m in MODELOS)


def test_una_carrera_con_la_misma_clave_se_resuelve_sin_duplicar(fabrica, armar_estado, monkeypatch):
    caso, nodo = _caso(CASO_ALERTAS), _nodo(fabrica)
    nodo(armar_estado(caso))
    monkeypatch.setattr(modulo, "_existe", lambda _s, _c: False)     # la 2.ª no ve a la 1.ª

    out = nodo(armar_estado(caso))

    assert out["estado_nodos"] == {"persistencia": "ya_guardado"}
    assert _n(fabrica, PaseTurno) == 1
