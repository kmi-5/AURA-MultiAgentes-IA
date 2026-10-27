"""Corre UN turno completo contra Neon (PostgresSaver) y, opcionalmente, Gemini real (paso 2.9).

  uv run python -m backend.app.core.demo_turno --caso 3 --aprobar --sin-llm   # solo infraestructura
  uv run python -m backend.app.core.demo_turno --caso 3 --aprobar             # con Gemini real

Usa los pacientes del seed. SOLO entorno dev: nunca con datos de pacientes reales.
"""
import argparse
import logging
import os
import time
import uuid
from datetime import date

from langgraph.types import Command
from sqlalchemy import func, select

from .observabilidad import activar_langsmith
from ..data.casos_prueba import CASOS, entrada_de
from ..graph.ensamblado import armar_grafo
from ..models.db_models import AlertaSeguridad, Paciente, PaseTurno, UsuarioEnfermeria
from .checkpointer import get_checkpointer, get_pool, make_thread_id
from .config import settings
from .db import SessionLocal
from .llm import crear_redactores


def main() -> None:
    logging.basicConfig(level=logging.WARNING)     # deja ver si el LLM falló y se usó el fallback
    ap = argparse.ArgumentParser()
    ap.add_argument("--caso", type=int, default=3, help="1..10: paciente del seed")
    ap.add_argument("--aprobar", action="store_true", help="aprueba el turno al final")
    ap.add_argument("--sin-llm", action="store_true", help="sin llamadas a Gemini")
    ap.add_argument("--sin-traza", action="store_true", help="no enviar la traza a LangSmith")
    ap.add_argument("--limpiar-hilo", action="store_true", help="borra los checkpoints de este paciente-turno-día antes de correr (pase sin historial previo)")
    args = ap.parse_args()


    caso = CASOS[args.caso - 1]
    with SessionLocal() as s:
        paciente_id = s.scalar(select(Paciente.id).where(Paciente.nombre == caso["nombre"]))
        usuario_id = s.scalar(select(UsuarioEnfermeria.id)
                              .where(UsuarioEnfermeria.username == "enfermera1"))
    if paciente_id is None or usuario_id is None:
        raise SystemExit("Faltan datos del seed: corré "
                         "`uv run python -m backend.app.core.seed --reset`")

    if not args.sin_traza:
        activar_langsmith()
    redactor_alertas = redactor_evolucion = None
    if not args.sin_llm:
        redactor_alertas, redactor_evolucion = crear_redactores(settings.google_api_key)

    clave = uuid.uuid4().hex
    config = {"configurable": {"thread_id": make_thread_id(paciente_id, "manana", date.today())}}
    inicio = {"paciente_id": paciente_id, "turno": "manana", "usuario_id": usuario_id,
              "idempotency_key": clave, "entrada_cruda": entrada_de(caso, paciente_id)}

    try:
        checkpointer = get_checkpointer()
        checkpointer.setup()                         
        if args.limpiar_hilo:
            checkpointer.delete_thread(config["configurable"]["thread_id"])
        grafo = armar_grafo(checkpointer=checkpointer, redactor_alertas=redactor_alertas,
                            redactor_evolucion=redactor_evolucion)

        t0 = time.perf_counter()
        grafo.invoke(inicio, config)
        v = grafo.get_state(config).values
        print(f"\n== {caso['nombre']} | hasta la aprobación en {time.perf_counter() - t0:.1f} s ==")
        print("estado_nodos:", v.get("estado_nodos"))
        print("requiere_revision:", v.get("requiere_revision"),
              "| turno_incompleto:", v.get("turno_incompleto"))
        print("puntajes:", v.get("puntajes_escalas"), "| avisos:", v.get("avisos_seguridad"))
        for a in v.get("alertas_actuales", []):
            print(f"  - {a.tipo_alerta} ({a.severidad}): {a.descripcion}")
        print("evolución:", v.get("evolucion"))

        if not args.aprobar:
            print("\nQuedó esperando aprobación. Volvé a correr con --aprobar.")
            return

        grafo.invoke(Command(resume={"decision": "aprobado"}), config)
    finally:
        get_pool().close()                           # es un proceso aparte: se cierra al terminar

    with SessionLocal() as s:
        pase = s.scalars(select(PaseTurno).where(PaseTurno.idempotency_key == clave)).first()
        n_alertas = s.scalar(select(func.count()).select_from(AlertaSeguridad)
                             .where(AlertaSeguridad.paciente_id == paciente_id))
    print(f"\nGuardado en Neon: pase={'sí' if pase else 'NO'} | alertas del paciente: {n_alertas}")
    if pase:
        print("\n" + pase.contenido_consolidado)


if __name__ == "__main__":
    main()
