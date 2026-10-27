from backend.app.data.casos_prueba import CASOS, entrada_de

CASO = next(c for c in CASOS if c["escenario"] == "hipertermia_taquicardia_y_taquipnea")


def _turno_aprobado(client, auth_headers) -> str:
    tid = client.post("/turnos/procesar", json=entrada_de(CASO, 1),
                      headers=auth_headers("enfermeria", "clave-cons-proc1")).json()["thread_id"]
    r = client.post(f"/turnos/{tid}/decision", json={"decision": "aprobado"},
                    headers=auth_headers("enfermeria", "clave-cons-dec01"))
    assert r.status_code == 200, r.text
    return tid


def test_pase_alertas_y_tareas_del_paciente(client, auth_headers):
    _turno_aprobado(client, auth_headers)
    pase = client.get("/pacientes/1/pase", headers=auth_headers("auditoria"))
    assert pase.status_code == 200 and pase.json()["contenido_consolidado"]
    assert pase.json()["turno"] == "manana"

    alertas = client.get("/pacientes/1/alertas", headers=auth_headers("auditoria")).json()
    assert len(alertas) == len(CASO["alertas_esperadas"])
    assert all(a["version_reglas"] and a["estado_revision"] == "pendiente" for a in alertas)

    tareas = client.get("/pacientes/1/tareas", headers=auth_headers("enfermeria")).json()
    assert tareas and all(t["estado"] == "pendiente" for t in tareas)
    assert [t["horario"] for t in tareas] == sorted(t["horario"] for t in tareas)


def test_consultar_el_turno_por_thread_id(client, auth_headers):
    tid = _turno_aprobado(client, auth_headers)
    r = client.get(f"/turnos/{tid}", headers=auth_headers("enfermeria"))
    assert r.status_code == 200 and r.json()["estado"] == "completado"
    assert client.get("/turnos/999:manana:2026-01-01", headers=auth_headers("enfermeria")).status_code == 404


def test_404_sin_pase_y_paciente_inexistente(client, auth_headers):
    assert client.get("/pacientes/2/pase", headers=auth_headers("enfermeria")).status_code == 404
    assert client.get("/pacientes/999/pase", headers=auth_headers("enfermeria")).status_code == 404
    assert client.get("/pacientes/999/alertas", headers=auth_headers("enfermeria")).status_code == 404


def test_rol_auditoria_no_ve_tareas(client, auth_headers):
    assert client.get("/pacientes/1/tareas", headers=auth_headers("auditoria")).status_code == 403


def test_listado_de_pacientes_con_paginacion(client, auth_headers):
    h = auth_headers("enfermeria")
    assert len(client.get("/pacientes", headers=h).json()) == 5
    assert len(client.get("/pacientes?limit=2", headers=h).json()) == 2
    assert client.get("/pacientes?limit=500", headers=h).status_code == 422


def test_auditoria_solo_para_supervision_y_auditoria(client, auth_headers):
    _turno_aprobado(client, auth_headers)
    assert client.get("/auditoria", headers=auth_headers("enfermeria")).status_code == 403
    r = client.get("/auditoria?tarea=decision_turno", headers=auth_headers("supervision"))
    assert r.status_code == 200 and len(r.json()) == 1
    assert r.json()[0]["detalle"]["decision"] == "aprobado"
    assert client.get("/auditoria", headers=auth_headers("auditoria")).status_code == 200
    assert client.get("/auditoria?limit=1000", headers=auth_headers("auditoria")).status_code == 422
