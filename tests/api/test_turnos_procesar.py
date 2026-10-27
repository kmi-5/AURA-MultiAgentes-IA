from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.app.core.idempotencia import huella_payload
from backend.app.data.casos_prueba import CASOS, entrada_de
from backend.app.models.db_models import Idempotencia, UsuarioEnfermeria
from backend.app.models.schemas import DatosEntrada

CASO = next(c for c in CASOS if c["escenario"] == "hipertermia_taquicardia_y_taquipnea")   # 5 alertas, 1 medicación


def payload(paciente_id: int = 1) -> dict:
    return entrada_de(CASO, paciente_id)


def test_procesar_deja_el_turno_pendiente_de_aprobacion(client, auth_headers):
    r = client.post("/turnos/procesar", json=payload(), headers=auth_headers("enfermeria", "clave-proc-0001"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["estado"] == "pendiente_aprobacion"
    assert d["thread_id"].startswith("1:manana:")
    assert len(d["revision"]["alertas"]) == len(CASO["alertas_esperadas"])
    assert d["revision"]["requiere_revision"] is True
    assert r.headers["X-Request-ID"]


def test_doble_click_no_vuelve_a_ejecutar_el_grafo(client, grafo, auth_headers):
    h = auth_headers("enfermeria", "clave-doble-0001")
    a = client.post("/turnos/procesar", json=payload(), headers=h)
    b = client.post("/turnos/procesar", json=payload(), headers=h)
    assert a.status_code == b.status_code == 200
    assert b.headers["Idempotent-Replay"] == "true"
    assert a.json() == b.json()
    assert grafo.invocaciones == 1


def test_misma_clave_con_otro_contenido_da_422(client, auth_headers):
    h = auth_headers("enfermeria", "clave-reuso-0001")
    assert client.post("/turnos/procesar", json=payload(1), headers=h).status_code == 200
    assert client.post("/turnos/procesar", json=payload(2), headers=h).status_code == 422


def test_clave_en_proceso_da_409(client, session_factory, auth_headers):
    h = auth_headers("enfermeria", "clave-en-curso-1")
    huella = huella_payload(DatosEntrada.model_validate(payload()).model_dump(mode="json"))
    ahora = datetime.now(timezone.utc)
    with session_factory() as db:
        uid = db.scalar(select(UsuarioEnfermeria.id).where(UsuarioEnfermeria.rol == "enfermeria"))
        db.add(Idempotencia(usuario_id=uid, endpoint="procesar", clave="clave-en-curso-1", huella=huella,
                            estado="en_proceso", creado_en=ahora, expira_en=ahora + timedelta(hours=1)))
        db.commit()
    assert client.post("/turnos/procesar", json=payload(), headers=h).status_code == 409


def test_otra_clave_mientras_hay_aprobacion_pendiente_da_409(client, auth_headers):
    assert client.post("/turnos/procesar", json=payload(), headers=auth_headers("enfermeria", "clave-uno-00001")).status_code == 200
    r = client.post("/turnos/procesar", json=payload(), headers=auth_headers("enfermeria", "clave-dos-00001"))
    assert r.status_code == 409


def test_pacientes_distintos_no_se_bloquean(client, auth_headers):
    assert client.post("/turnos/procesar", json=payload(1), headers=auth_headers("enfermeria", "clave-pac1-0001")).status_code == 200
    assert client.post("/turnos/procesar", json=payload(2), headers=auth_headers("enfermeria", "clave-pac2-0001")).status_code == 200


def test_paciente_inexistente_da_404(client, auth_headers):
    r = client.post("/turnos/procesar", json=payload(999), headers=auth_headers("enfermeria", "clave-404-00001"))
    assert r.status_code == 404


def test_sin_idempotency_key_da_422(client, auth_headers):
    h = auth_headers("enfermeria")
    del h["Idempotency-Key"]
    assert client.post("/turnos/procesar", json=payload(), headers=h).status_code == 422


def test_clave_demasiado_corta_da_422(client, auth_headers):
    assert client.post("/turnos/procesar", json=payload(), headers=auth_headers("enfermeria", "corta")).status_code == 422


def test_fallo_del_grafo_da_502_y_libera_la_clave(client, grafo, auth_headers, monkeypatch):
    h = auth_headers("enfermeria", "clave-falla-0001")

    def falla(*a, **k):
        raise RuntimeError("boom")

    with monkeypatch.context() as m:
        m.setattr(grafo, "invoke", falla)
        assert client.post("/turnos/procesar", json=payload(), headers=h).status_code == 502
    assert client.post("/turnos/procesar", json=payload(), headers=h).status_code == 200   # misma clave: reintento válido
