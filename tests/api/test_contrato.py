import time

from backend.app.data.casos_prueba import CASOS, entrada_de

RUTAS = ["/auth/login", "/turnos/procesar", "/turnos/{thread_id}/decision", "/turnos/{thread_id}",
         "/pacientes", "/pacientes/{paciente_id}/pase", "/pacientes/{paciente_id}/tareas",
         "/pacientes/{paciente_id}/alertas", "/auditoria", "/health"]


def test_openapi_documenta_todas_las_rutas(client):
    paths = client.get("/openapi.json").json()["paths"]
    for ruta in RUTAS:
        assert ruta in paths, f"falta {ruta} en el contrato"


def test_health_con_base_disponible(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"estado": "ok"}


def test_latencia_de_procesar_con_mocks_menor_a_3_segundos(client, auth_headers):
    h = auth_headers("enfermeria", "clave-lat-000001")
    inicio = time.perf_counter()
    r = client.post("/turnos/procesar", json=entrada_de(CASOS[2], 1), headers=h)
    assert r.status_code == 200
    assert time.perf_counter() - inicio < 3.0        # criterio de aceptación (sección 13.1)
