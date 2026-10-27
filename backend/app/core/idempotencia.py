import hashlib
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import FlushError

from ..models.db_models import Idempotencia
from .config import settings


def huella_payload(payload: dict) -> str:
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def reclamar(db, usuario_id: int, endpoint: str, clave: str, huella: str, _reintento: bool = True):
    """Devuelve (resultado, registro): 'nuevo' | 'repetido' | 'en_proceso' | 'conflicto'."""
    ahora = datetime.now(timezone.utc)
    db.add(Idempotencia(usuario_id=usuario_id, endpoint=endpoint, clave=clave, huella=huella,
                        estado="en_proceso", creado_en=ahora,
                        expira_en=ahora + timedelta(hours=settings.idempotencia_ttl_horas)))
    try:
        db.commit()
        return "nuevo", None
    except (IntegrityError, FlushError):
        db.rollback()

    existente = db.get(Idempotencia, (usuario_id, endpoint, clave))
    if existente is None:                 # carrera: lo borraron justo ahora
        return "en_proceso", None
    expira = existente.expira_en
    if expira.tzinfo is None:             # SQLite devuelve fechas sin zona
        expira = expira.replace(tzinfo=timezone.utc)
    if expira < ahora and _reintento:
        db.delete(existente)
        db.commit()
        return reclamar(db, usuario_id, endpoint, clave, huella, _reintento=False)
    if existente.huella != huella:
        return "conflicto", existente
    return ("repetido" if existente.estado == "completada" else "en_proceso"), existente


def completar(db, usuario_id: int, endpoint: str, clave: str, status_code: int, respuesta: dict) -> None:
    reg = db.get(Idempotencia, (usuario_id, endpoint, clave))
    reg.estado, reg.status_code, reg.respuesta = "completada", status_code, respuesta
    db.commit()


def liberar(db, usuario_id: int, endpoint: str, clave: str) -> None:
    """Ante un fallo se libera la clave para que el cliente pueda reintentar."""
    reg = db.get(Idempotencia, (usuario_id, endpoint, clave))
    if reg and reg.estado == "en_proceso":
        db.delete(reg)
        db.commit()
