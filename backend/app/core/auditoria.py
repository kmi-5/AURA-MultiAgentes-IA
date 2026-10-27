from sqlalchemy.orm import Session

from ..models.db_models import Auditoria


class TareaAuditoria:
    LOGIN = "login"
    LOGIN_FALLIDO = "login_fallido"
    PROCESAR = "procesar_turno"
    DECISION = "decision_turno"
    RECHAZO_SANITIZADOR = "sanitizador_rechazo"


def registrar(db: Session, *, usuario_id: int | None, tarea: str, estado: str,
              detalle: dict | None = None, request_id: str | None = None) -> None:
    db.add(Auditoria(usuario_id=usuario_id, tarea=tarea, estado=estado,
                     detalle=detalle, request_id=request_id))
    db.commit()           # el timestamp lo pone el server_default