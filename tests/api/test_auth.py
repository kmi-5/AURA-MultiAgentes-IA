import time

import jwt
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.seguridad import decodificar_token
from backend.app.models.db_models import Auditoria


def _filas(sf, tarea):
    with sf() as db:
        return db.scalars(select(Auditoria).where(Auditoria.tarea == tarea)).all()


def test_login_ok_devuelve_token_con_rol(client, passwords):
    r = client.post("/auth/login", json={"username": "enfermeria.test", "password": passwords["enfermeria"]})
    assert r.status_code == 200 and r.json()["token_type"] == "bearer"
    assert decodificar_token(r.json()["access_token"])["rol"] == "enfermeria"


def test_login_fallido_mismo_mensaje_para_clave_mala_y_usuario_inexistente(client, session_factory):
    mala = client.post("/auth/login", json={"username": "enfermeria.test", "password": "incorrecta"})
    nadie = client.post("/auth/login", json={"username": "no.existe", "password": "incorrecta"})
    assert mala.status_code == nadie.status_code == 401
    assert mala.json() == nadie.json()
    filas = _filas(session_factory, "login_fallido")
    assert len(filas) == 2
    assert {f.usuario_id is None for f in filas} == {True, False}    # el inexistente queda con usuario_id nulo


def test_sin_token_da_401_antes_que_422(client):
    assert client.post("/turnos/procesar", json={}).status_code == 401


def test_token_manipulado_da_401(client, auth_headers):
    h = auth_headers("enfermeria")
    h["Authorization"] = h["Authorization"][:-3] + "abc"
    assert client.post("/turnos/procesar", json={}, headers=h).status_code == 401


def test_token_expirado_da_401(client):
    t = jwt.encode({"sub": "1", "nombre": "x", "rol": "enfermeria", "exp": int(time.time()) - 10},
                   settings.jwt_secret, algorithm=settings.jwt_algoritmo)
    r = client.post("/turnos/procesar", json={}, headers={"Authorization": f"Bearer {t}"})
    assert r.status_code == 401 and "expirado" in r.json()["detail"].lower()


def test_rol_auditoria_no_puede_procesar(client, auth_headers):
    assert client.post("/turnos/procesar", json={}, headers=auth_headers("auditoria")).status_code == 403