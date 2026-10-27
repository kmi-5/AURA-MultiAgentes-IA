import time

import jwt
import pytest

from backend.app.core.config import settings
from backend.app.core.seguridad import (
    crear_token, decodificar_token, hashear_password, verificar_password,
)


def test_hash_y_verificacion():
    h = hashear_password("clave-larga-123")
    assert h != "clave-larga-123"
    assert verificar_password("clave-larga-123", h)
    assert not verificar_password("otra-clave", h)


def test_hash_con_formato_desconocido_no_explota():
    assert verificar_password("x", "x") is False


def test_usuario_inexistente_devuelve_false():
    assert verificar_password("x", None) is False


def test_token_ida_y_vuelta():
    token, expira = crear_token(7, "Ana", "enfermeria")
    d = decodificar_token(token)
    assert d["sub"] == "7" and d["rol"] == "enfermeria" and d["nombre"] == "Ana"
    assert expira == settings.jwt_expira_minutos * 60


def test_token_firmado_con_otro_secreto_se_rechaza():
    malo = jwt.encode({"sub": "1", "rol": "enfermeria", "exp": int(time.time()) + 60},
                      "otro-secreto-distinto-" + "y" * 32, algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        decodificar_token(malo)


def test_token_sin_firma_alg_none_se_rechaza():
    sin_firma = jwt.encode({"sub": "1", "rol": "enfermeria", "exp": int(time.time()) + 60},
                           None, algorithm="none")
    with pytest.raises(jwt.InvalidTokenError):
        decodificar_token(sin_firma)


def test_token_sin_rol_se_rechaza():
    sin_rol = jwt.encode({"sub": "1", "exp": int(time.time()) + 60},
                         settings.jwt_secret, algorithm=settings.jwt_algoritmo)
    with pytest.raises(jwt.InvalidTokenError):
        decodificar_token(sin_rol)
