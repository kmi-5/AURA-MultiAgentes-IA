import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.agents.documentacion import crear_redactor_evolucion
from backend.app.agents.redactor import crear_redactor
from backend.app.core.db import Base
from backend.app.data.casos_limite import CASOS_LIMITE
from backend.app.data.casos_prueba import CASOS, entrada_de
from backend.app.graph.ensamblado import armar_grafo
from backend.app.models.db_models import (
    AlertaSeguridad, Auditoria, Paciente, PaseTurno, Tarea, UsuarioEnfermeria,
)

TODOS = CASOS + CASOS_LIMITE
DESCRIPCION_FAKE = "Hallazgo registrado que requiere revisión por enfermería."
EVOLUCION_FAKE = ("Registro de enfermería del turno elaborado con los datos ingresados, "
                  "sin particularidades adicionales.")
EDITADA = "Evolución corregida por la enfermera."


@pytest.fixture
def fabrica():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    f = sessionmaker(engine, expire_on_commit=False)
    with f.begin() as s:
        s.add(UsuarioEnfermeria(nombre="Enfermera", username="enf", rol="enfermeria",
                                password_hash="x"))
        for i in range(1, 6):
            s.add(Paciente(nombre=f"Paciente {i}", edad=60, habitacion=str(100 + i)))
    yield f
    engine.dispose()


class FabricaInestable:
    """Falla la primera vez que abre una transacción: una caída momentánea de la base."""
    def __init__(self, real):
        self.real, self.fallos = real, 1

    def begin(self):
        if self.fallos:
            self.fallos -= 1
            raise OperationalError("INSERT", {}, Exception("base no disponible"))
        return self.real.begin()


def _caso(escenario):
    return next(c for c in TODOS if c["escenario"] == escenario)


def _grafo(fabrica, *, edad=60, **kwargs):
    return armar_grafo(checkpointer=MemorySaver(), obtener_edad=lambda _pid: edad,
                       session_factory=fabrica, **kwargs)


def _config(pid=1, hilo="t"):
    return {"configurable": {"thread_id": f"{pid}:manana:{hilo}"}}


def _inicio(caso, pid=1, clave="k1"):
    return {"paciente_id": pid, "turno": "manana", "usuario_id": 1,
            "idempotency_key": clave, "entrada_cruda": entrada_de(caso, pid)}


def _aprobar(grafo, config, **resume):
    return grafo.invoke(Command(resume=resume or {"decision": "aprobado"}), config)


def _contar(fabrica, modelo):
    with fabrica() as s:
        return s.scalar(select(func.count()).select_from(modelo))


# --- golden set completo, de la entrada a la base ---

@pytest.mark.parametrize("caso", TODOS, ids=lambda c: c["escenario"])
def test_el_golden_set_atraviesa_el_grafo_y_se_guarda(fabrica, caso):
    grafo = _grafo(fabrica, edad=caso["edad"])
    grafo.invoke(_inicio(caso), _config())
    _aprobar(grafo, _config())

    with fabrica() as s:
        guardadas = {a.tipo_alerta for a in s.scalars(select(AlertaSeguridad))}
        pase = s.scalars(select(PaseTurno)).one()
        auditoria = s.scalars(select(Auditoria)).one()

    assert guardadas == caso["alertas_esperadas"]
    assert pase.incompleto is False and "PASE DE GUARDIA" in pase.contenido_consolidado
    assert auditoria.tarea == "turno_aprobado"
    assert grafo.get_state(_config()).next == ()


# --- con los LLM simulados ---

def test_con_los_llm_simulados_el_texto_del_modelo_llega_a_la_base_y_al_pase(fabrica):
    caso = _caso("hipertermia_taquicardia_y_taquipnea")
    grafo = _grafo(
        fabrica, edad=caso["edad"],
        redactor_alertas=crear_redactor(
            lambda _p: json.dumps({"descripcion": DESCRIPCION_FAKE}), sleep=lambda _s: None),
        redactor_evolucion=crear_redactor_evolucion(
            lambda _p: json.dumps({"evolucion": EVOLUCION_FAKE}), sleep=lambda _s: None),
    )
    grafo.invoke(_inicio(caso), _config())
    _aprobar(grafo, _config())

    with fabrica() as s:
        descripciones = {a.descripcion for a in s.scalars(select(AlertaSeguridad))}
        pase = s.scalars(select(PaseTurno)).one()
    assert descripciones == {DESCRIPCION_FAKE}
    assert EVOLUCION_FAKE in pase.contenido_consolidado


def test_si_los_llm_estan_caidos_se_guarda_igual_con_el_texto_determinista(fabrica):
    caso = _caso("hipertermia_taquicardia_y_taquipnea")

    def caido(_prompt):
        raise RuntimeError("Gemini no responde")

    grafo = _grafo(fabrica, edad=caso["edad"],
                   redactor_alertas=crear_redactor(caido, sleep=lambda _s: None),
                   redactor_evolucion=crear_redactor_evolucion(caido, sleep=lambda _s: None))
    grafo.invoke(_inicio(caso), _config())
    _aprobar(grafo, _config())

    with fabrica() as s:
        guardadas = {a.tipo_alerta for a in s.scalars(select(AlertaSeguridad))}
        pase = s.scalars(select(PaseTurno)).one()
    assert guardadas == caso["alertas_esperadas"]
    assert "Evolución: Paciente de 55 años" in pase.contenido_consolidado


# --- idempotencia, decisión humana y fallos ---

def test_reenviar_el_mismo_turno_no_duplica_registros(fabrica):
    caso = _caso("hipertermia_taquicardia_y_taquipnea")
    grafo = _grafo(fabrica, edad=caso["edad"])
    for _ in range(2):                                    # doble click en "Procesar turno"
        grafo.invoke(_inicio(caso, clave="mismo"), _config())
        _aprobar(grafo, _config())

    assert _contar(fabrica, PaseTurno) == 1
    assert _contar(fabrica, AlertaSeguridad) == len(caso["alertas_esperadas"])
    assert _contar(fabrica, Auditoria) == 1


def test_descartar_solo_deja_auditoria(fabrica):
    caso = _caso("hipertermia_taquicardia_y_taquipnea")
    grafo = _grafo(fabrica, edad=caso["edad"])
    grafo.invoke(_inicio(caso), _config())
    _aprobar(grafo, _config(), decision="descartado")

    assert _contar(fabrica, PaseTurno) == 0 and _contar(fabrica, AlertaSeguridad) == 0
    with fabrica() as s:
        assert s.scalars(select(Auditoria)).one().tarea == "turno_descartado"


def test_editar_deja_el_texto_de_la_enfermera_en_el_pase(fabrica):
    caso = _caso("hipertermia_taquicardia_y_taquipnea")
    grafo = _grafo(fabrica, edad=caso["edad"])
    grafo.invoke(_inicio(caso), _config())
    _aprobar(grafo, _config(), decision="editado", evolucion_editada=EDITADA)

    with fabrica() as s:
        pase = s.scalars(select(PaseTurno)).one()
        assert s.scalars(select(Auditoria)).one().tarea == "turno_editado"
    assert f"Evolución: {EDITADA}" in pase.contenido_consolidado
    assert "editado por la enfermera" in pase.contenido_consolidado


def test_un_timeout_de_seguridad_se_guarda_como_turno_incompleto(fabrica):
    caso = _caso("dolor_intenso")                         # una sola alerta

    def lento(_alerta):
        time.sleep(0.6)
        return "Texto."

    grafo = _grafo(fabrica, edad=caso["edad"], timeout_s=0.1, redactor_alertas=lento)
    grafo.invoke(_inicio(caso), _config())
    _aprobar(grafo, _config())

    with fabrica() as s:
        pase = s.scalars(select(PaseTurno)).one()
        revision = s.scalar(select(func.count()).select_from(Tarea).where(Tarea.tipo == "revision"))
    assert pase.incompleto is True and "no disponibles" in pase.contenido_consolidado
    assert _contar(fabrica, AlertaSeguridad) == 0         # no se guardan alertas de una rama caída
    assert revision == 1                                  # sin Seguridad se fuerza la revisión


def test_si_persistencia_falla_se_reintenta_sin_repetir_la_aprobacion(fabrica):
    caso = _caso("hipertermia_taquicardia_y_taquipnea")
    grafo = _grafo(FabricaInestable(fabrica), edad=caso["edad"])
    config = _config()

    grafo.invoke(_inicio(caso), config)
    with pytest.raises(OperationalError):
        _aprobar(grafo, config)
    assert grafo.get_state(config).next == ("persistencia",)

    grafo.invoke(None, config)                            # retoma desde el nodo que falló
    assert grafo.get_state(config).next == ()
    assert _contar(fabrica, PaseTurno) == 1


# --- varias ejecuciones, varios pacientes y latencia ---

def test_dos_ejecuciones_del_mismo_turno_acumulan_el_pase(fabrica):
    grafo = _grafo(fabrica)
    for caso, clave in ((_caso("saturacion_baja_y_taquipnea"), "k1"), (CASOS[0], "k2")):
        grafo.invoke(_inicio(caso, clave=clave), _config())
        _aprobar(grafo, _config())

    with fabrica() as s:
        pases = s.scalars(select(PaseTurno).order_by(PaseTurno.id)).all()
    assert len(pases) == 2
    assert "Registros del turno: 1" in pases[0].contenido_consolidado
    assert "Registros del turno: 2" in pases[1].contenido_consolidado
    assert "saturacion_baja" in pases[1].contenido_consolidado     # arrastra el primer registro


def test_varios_pacientes_en_simultaneo_no_se_mezclan(fabrica):
    grafo = _grafo(fabrica)
    pacientes = [(1, "dolor_intenso"), (2, "hipertension"), (3, "estable_sin_alertas"),
                 (4, "hipotension_y_taquicardia")]

    def correr(par):
        pid, escenario = par
        grafo.invoke(_inicio(_caso(escenario), pid=pid, clave=f"k{pid}"), _config(pid))
        valores = grafo.get_state(_config(pid)).values
        return pid, {a.tipo_alerta for a in valores["alertas_actuales"]}

    with ThreadPoolExecutor(max_workers=4) as pool:
        esperadas = dict(pool.map(correr, pacientes))
    for pid, _ in pacientes:
        _aprobar(grafo, _config(pid))

    assert esperadas == {1: {"dolor_severo"}, 2: {"hipertension"}, 3: set(),
                         4: {"hipotension", "taquicardia", "news2_rojo_unico", "news2_alto"}}
    with fabrica() as s:
        guardadas = {pid: {a.tipo_alerta for a in s.scalars(
            select(AlertaSeguridad).where(AlertaSeguridad.paciente_id == pid))}
            for pid, _ in pacientes}
    assert guardadas == esperadas


def test_el_turno_llega_a_la_aprobacion_en_pocos_segundos(fabrica):
    grafo = _grafo(fabrica)
    t0 = time.perf_counter()
    grafo.invoke(_inicio(CASOS[1]), _config())
    assert time.perf_counter() - t0 < 3.0                 # criterio de aceptación
