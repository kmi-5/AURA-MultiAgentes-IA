import uuid
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from .config import settings

_hasher = PasswordHash.recommended()
_HASH_DUMMY = _hasher.hash("relleno-para-igualar-tiempos")


def hashear_password(p: str) -> str:
    return _hasher.hash(p)


def verificar_password(p: str, hash_guardado: str | None) -> bool:
    if hash_guardado is None:            
        _hasher.verify(p, _HASH_DUMMY)
        return False
    try:
        return _hasher.verify(p, hash_guardado)
    except Exception:                  
        return False


def crear_token(usuario_id: int, nombre: str, rol: str) -> tuple[str, int]:
    ahora = datetime.now(timezone.utc)
    exp = ahora + timedelta(minutes=settings.jwt_expira_minutos)
    payload = {"sub": str(usuario_id), "nombre": nombre, "rol": rol,
               "iat": ahora, "exp": exp, "jti": uuid.uuid4().hex}
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algoritmo)
    return token, settings.jwt_expira_minutos * 60


def decodificar_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algoritmo],
                      options={"require": ["exp", "sub", "rol"]})
