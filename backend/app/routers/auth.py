from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select

from ..core.auditoria import TareaAuditoria, registrar
from ..core.seguridad import crear_token, verificar_password
from ..models.db_models import UsuarioEnfermeria
from .deps import get_db

router = APIRouter(prefix="/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/login", response_model=TokenOut)
@limiter.limit("5/minute")
def login(request: Request, datos: LoginIn, db=Depends(get_db)):
    u = db.scalar(select(UsuarioEnfermeria).where(UsuarioEnfermeria.username == datos.username))
    ok = verificar_password(datos.password, u.password_hash if u else None)
    rid = getattr(request.state, "request_id", None)
    if not (u and ok):
        registrar(db, usuario_id=u.id if u else None, tarea=TareaAuditoria.LOGIN_FALLIDO,
                  estado="error", detalle={"username": datos.username[:50]}, request_id=rid)
        raise HTTPException(401, "Credenciales inválidas")      # mismo mensaje en ambos casos
    token, expira = crear_token(u.id, u.nombre, u.rol)
    registrar(db, usuario_id=u.id, tarea=TareaAuditoria.LOGIN, estado="ok", request_id=rid)
    return TokenOut(access_token=token, expires_in=expira)