import base64
import json
from types import SimpleNamespace

import pytest

import sesion


def jwt(claims):
    b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{b({'alg': 'HS256'})}.{b(claims)}.firma"


@pytest.fixture
def estado(monkeypatch):
    fake = SimpleNamespace(session_state={})
    monkeypatch.setattr(sesion, "st", fake)
    return fake.session_state


def test_iniciar_lee_rol_del_token(estado):
    sesion.iniciar(jwt({"rol": "Supervisión", "nombre": "Ana"}), "supervisor1")
    assert sesion.rol() == "supervision" and sesion.usuario() == "Ana"
    assert sesion.puede_operar() and sesion.ve_auditoria()


def test_auditoria_solo_lee(estado):
    sesion.iniciar(jwt({"rol": "auditoria"}), "auditor1")
    assert not sesion.puede_operar() and sesion.ve_auditoria()


def test_enfermeria_opera_y_no_ve_auditoria(estado):
    sesion.iniciar(jwt({"rol": "enfermeria"}), "enfermera1")
    assert sesion.puede_operar() and not sesion.ve_auditoria()


def test_token_ilegible_no_rompe(estado):
    sesion.iniciar("no-es-jwt", "x", rol="enfermeria")
    assert sesion.rol() == "enfermeria" and sesion.autenticado()


def test_cerrar_borra_todo(estado):
    sesion.iniciar(jwt({"rol": "enfermeria"}), "e")
    sesion.cerrar()
    assert not sesion.autenticado()


def test_clave_se_reutiliza_con_el_mismo_contenido(estado):
    k1 = sesion.clave_para("h1")
    assert sesion.clave_para("h1") == k1
    assert sesion.clave_para("h2") != k1


def test_clave_nueva_tras_liberar(estado):
    k1 = sesion.clave_para("h1")
    sesion.liberar_clave()
    assert sesion.clave_para("h1") != k1
