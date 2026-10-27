"""Prueba de humo de la API contra un servidor real levantado.

  Terminal 1:  GOOGLE_API_KEY= uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8000   # sin Gemini
  Terminal 2:  uv run python -m backend.app.core.smoke_api

Variables: AURA_PASS (obligatoria), AURA_USER (enfermera1), AURA_CASO (3), AURA_URL.
SOLO entorno dev: nunca con datos de pacientes reales.
"""
import os
import sys
import time
import uuid

import httpx

from ..data.casos_prueba import CASOS, entrada_de

BASE = os.getenv("AURA_URL", "http://127.0.0.1:8000")
USER = os.getenv("AURA_USER", "enfermera1")
PASSWORD = os.getenv("AURA_PASS")
CASO = CASOS[int(os.getenv("AURA_CASO", "3")) - 1]


def verificar(condicion: bool, mensaje: str) -> None:
    print(("OK    " if condicion else "FALLA ") + mensaje)
    if not condicion:
        sys.exit(1)


def main() -> None:
    if not PASSWORD:
        sys.exit("Falta AURA_PASS. Usá:  read -s AURA_PASS; export AURA_PASS")
    c = httpx.Client(base_url=BASE, timeout=120)

    verificar(c.get("/health").json() == {"estado": "ok"}, "health: la API ve la base de datos")
    verificar(c.post("/turnos/procesar", json={}).status_code == 401, "sin token -> 401")
    mala = c.post("/auth/login", json={"username": USER, "password": "incorrecta"})
    verificar(mala.status_code == 401, "contraseña incorrecta -> 401")
    r = c.post("/auth/login", json={"username": USER, "password": PASSWORD})
    verificar(r.status_code == 200, "login correcto")
    token = r.json()["access_token"]

    def h(clave: str | None = None) -> dict:
        return {"Authorization": f"Bearer {token}", "Idempotency-Key": clave or uuid.uuid4().hex}

    pacientes = c.get("/pacientes", headers=h()).json()
    paciente_id = next((p["id"] for p in pacientes if p["nombre"] == CASO["nombre"]), None)
    verificar(paciente_id is not None, f"paciente del seed: {CASO['nombre']}")

    clave = uuid.uuid4().hex
    t0 = time.perf_counter()
    r = c.post("/turnos/procesar", json=entrada_de(CASO, paciente_id), headers=h(clave))
    if r.status_code == 409:
        sys.exit("409: este paciente-turno quedó pendiente de un intento anterior. "
                 "Resolvelo desde /docs (POST /turnos/{thread_id}/decision) y volvé a correr.")
    verificar(r.status_code == 200, f"procesar en {time.perf_counter() - t0:.1f} s")
    turno = r.json()
    verificar(turno["estado"] == "pendiente_aprobacion", "queda pendiente de aprobación")
    print(f"      alertas: {[a['tipo_alerta'] for a in turno['revision']['alertas']]}")
    print(f"      evolución: {(turno['revision']['evolucion'] or '')[:100]}")

    t0 = time.perf_counter()
    r2 = c.post("/turnos/procesar", json=entrada_de(CASO, paciente_id), headers=h(clave))
    verificar(r2.headers.get("Idempotent-Replay") == "true" and r2.json() == turno,
              f"doble click: replay idéntico en {time.perf_counter() - t0:.2f} s")

    tid, clave_dec = turno["thread_id"], uuid.uuid4().hex
    r = c.post(f"/turnos/{tid}/decision", json={"decision": "aprobado"}, headers=h(clave_dec))
    verificar(r.status_code == 200 and r.json()["estado"] == "completado", "aprobar -> completado")
    r = c.post(f"/turnos/{tid}/decision", json={"decision": "aprobado"}, headers=h(clave_dec))
    verificar(r.headers.get("Idempotent-Replay") == "true", "doble click en la decisión: replay")
    r = c.post(f"/turnos/{tid}/decision", json={"decision": "aprobado"}, headers=h())
    verificar(r.status_code == 409, "decidir de nuevo con otra clave -> 409")

    pase = c.get(f"/pacientes/{paciente_id}/pase", headers=h())
    verificar(pase.status_code == 200 and bool(pase.json()["contenido_consolidado"]), "pase guardado en Neon")
    alertas = c.get(f"/pacientes/{paciente_id}/alertas", headers=h()).json()
    tareas = c.get(f"/pacientes/{paciente_id}/tareas", headers=h()).json()
    print(f"      alertas guardadas: {len(alertas)} | tareas: {len(tareas)}")
    print("\n" + pase.json()["contenido_consolidado"])
    print("\nTodo OK.")


if __name__ == "__main__":
    main()
