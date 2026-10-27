import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from ..core.seguridad import decodificar_token

bearer = HTTPBearer(auto_error=False)


class UsuarioActual(BaseModel):
    id: int
    nombre: str
    rol: str


def get_db(request: Request):
    with request.app.state.session_factory() as db:
        yield db


def get_grafo(request: Request):
    return request.app.state.grafo


def get_current_user(request: Request,
                     cred: HTTPAuthorizationCredentials | None = Depends(bearer)) -> UsuarioActual:
    cabecera = {"WWW-Authenticate": "Bearer"}
    if cred is None:
        raise HTTPException(401, "No autenticado", headers=cabecera)
    try:
        d = decodificar_token(cred.credentials)
        usuario = UsuarioActual(id=int(d["sub"]), nombre=d["nombre"], rol=d["rol"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expirado", headers=cabecera)
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(401, "Token inválido", headers=cabecera)
    request.state.usuario = usuario      # lo lee el handler de rechazos del sanitizador
    return usuario


def requiere_rol(*roles: str):
    def dep(u: UsuarioActual = Depends(get_current_user)) -> UsuarioActual:
        if u.rol not in roles:
            raise HTTPException(403, "Rol sin permiso para esta acción")
        return u
    return dep