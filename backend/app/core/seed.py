import argparse
import secrets
from datetime import time

from .seguridad import hashear_password as _hash
from sqlalchemy import func, select, text

from ..data.casos_prueba import CASOS
from ..models.db_models import (
    Auditoria,
    Medicacion,
    Paciente,
    SignosVitalesRow,
    Tarea,
    UsuarioEnfermeria,
    ValoracionCaidasRow,
)
from .config import settings
from .db import SessionLocal


TABLAS = (
    "idempotencia, auditoria, tareas, pases_turno, alertas_seguridad, medicacion, "
    "valoracion_caidas, signos_vitales, pacientes, usuarios_enfermeria"
)

TURNO_SEED = "manana"   # mismo default que entrada_de()


def run(reset: bool = False) -> None:
    generada = settings.seed_password is None
    password = settings.seed_password or secrets.token_urlsafe(9)

    with SessionLocal.begin() as s:
        if reset:
            s.execute(text(f"TRUNCATE {TABLAS} RESTART IDENTITY CASCADE"))
        elif s.scalar(select(func.count()).select_from(Paciente)):
            print("Ya hay pacientes cargados; no se hizo nada. (--reset recarga todo)")
            return

        enfermera = UsuarioEnfermeria(
            nombre="Enfermera Demo",
            username="enfermera1",
            rol="enfermeria",
            password_hash=_hash(password),
        )
        supervisor = UsuarioEnfermeria(
            nombre="Supervisor Demo",
            username="supervisor1",
            rol="supervision",
            password_hash=_hash(password),
        )
        auditor = UsuarioEnfermeria(
            nombre="Auditor Demo",
            username="auditor1",
            rol="auditoria",
            password_hash=_hash(password),
        )

        s.add_all([enfermera, supervisor, auditor])
        s.flush()

        for c in CASOS:
            p = Paciente(
                nombre=c["nombre"],
                edad=c["edad"],
                habitacion=c["habitacion"],
            )
            s.add(p)
            s.flush()

            s.add(SignosVitalesRow(paciente_id=p.id, **c["signos"]))

            # Ítems de Morse; el puntaje lo calcula el motor de reglas, no se guarda acá
            s.add(ValoracionCaidasRow(paciente_id=p.id, turno=TURNO_SEED, **c["caidas"]))

            for medicamento, dosis, frecuencia, hhmm in c["medicacion"]:
                horario = time.fromisoformat(hhmm)
                s.add(Medicacion(paciente_id=p.id, medicamento=medicamento, dosis=dosis,
                                 frecuencia=frecuencia, horario_programado=horario))
                s.add(Tarea(paciente_id=p.id, tipo="medicacion", horario=horario,
                            responsable_id=enfermera.id))

            s.add(Tarea(paciente_id=p.id, tipo="control", horario=time(12, 0),
                        responsable_id=enfermera.id))

        s.add(Auditoria(usuario_id=supervisor.id, tarea="seed_datos_prueba", estado="ok"))

    print(
        f"Seed OK: {len(CASOS)} pacientes y 3 usuarios "
        "(enfermera1, supervisor1, auditor1)."
    )

    if generada:
        print(
            "Contraseña generada para los 3 usuarios "
            f"(guardala, no se vuelve a mostrar): {password}"
        )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--reset",
        action="store_true",
        help="BORRA los datos de negocio y recarga el seed",
    )
    run(reset=ap.parse_args().reset)