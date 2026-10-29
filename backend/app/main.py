import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from .core.auditoria import TareaAuditoria, registrar
from .core.db import SessionLocal
from .core.sanitizar import TextoNoPermitido
from .routers import auth, consultas, turnos

logger = logging.getLogger("aura.api")


def _construir_grafo_real():
    from .core.checkpointer import get_checkpointer
    from .core.config import settings
    from .core.llm import crear_redactores
    from .core.observabilidad import activar_langsmith
    from .graph.ensamblado import armar_grafo

    activar_langsmith()
    checkpointer = get_checkpointer()
    checkpointer.setup()
    redactor_alertas = redactor_evolucion = None
    if settings.google_api_key:
        redactor_alertas, redactor_evolucion = crear_redactores(settings.google_api_key)
    else:
        logger.warning("Sin GOOGLE_API_KEY: la API corre con los redactores deterministas")
    return armar_grafo(checkpointer=checkpointer, redactor_alertas=redactor_alertas,
                       redactor_evolucion=redactor_evolucion)


def crear_app(*, session_factory=SessionLocal, grafo=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        propio = app.state.grafo is None
        if propio:
            app.state.grafo = _construir_grafo_real()
        yield
        if propio:
            from .core.checkpointer import get_pool
            get_pool().close()

    app = FastAPI(title="AURA API", version="0.3.0", lifespan=lifespan)
    app.state.session_factory = session_factory
    app.state.grafo = grafo
    app.state.limiter = auth.limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.middleware("http")
    async def request_id_y_log(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = rid
        inicio = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        # nunca body, ni Authorization, ni datos de pacientes
        logger.info("%s %s -> %s en %.0f ms rid=%s", request.method, request.url.path,
                    response.status_code, (time.perf_counter() - inicio) * 1000, rid)
        return response

    @app.exception_handler(RequestValidationError)
    async def validacion_handler(request: Request, exc: RequestValidationError):
        rechazos, errores = [], []
        for e in exc.errors():
            original = (e.get("ctx") or {}).get("error")
            if isinstance(original, TextoNoPermitido):
                campo = next((p for p in reversed(e["loc"]) if isinstance(p, str)), "desconocido")
                rechazos.append((campo, original))
                msg = "Texto no permitido"                     # sin eco del contenido
            else:
                msg = e["msg"]
            errores.append({"loc": list(e["loc"]), "msg": msg, "type": e["type"]})   # sin "input" ni "ctx"

        if rechazos:
            usuario = getattr(request.state, "usuario", None)
            rid = getattr(request.state, "request_id", None)

            def _auditar():
                with request.app.state.session_factory() as db:    # sesión propia
                    for campo, r in rechazos:
                        registrar(db, usuario_id=usuario.id if usuario else None,
                                  tarea=TareaAuditoria.RECHAZO_SANITIZADOR, estado="rechazado",
                                  detalle={"campo": campo, "regla": r.regla,
                                           "largo": r.largo, "sha256": r.sha256},
                                  request_id=rid)
            await run_in_threadpool(_auditar)
        return JSONResponse(status_code=422, content={"detail": errores})

    @app.exception_handler(Exception)
    async def error_generico(request: Request, exc: Exception):
        rid = getattr(request.state, "request_id", None)
        logger.error("Error no controlado rid=%s tipo=%s", rid, type(exc).__name__)
        return JSONResponse(status_code=500, content={"detail": "Error interno", "request_id": rid})

    @app.get("/health", tags=["sistema"])
    def health(request: Request):
        try:
            with request.app.state.session_factory() as db:
                db.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse(status_code=503, content={"estado": "sin_base_de_datos"})
        return {"estado": "ok"}

    @app.get("/live", tags=["sistema"])
    def live():
        return {"estado": "vivo"}
    app.include_router(auth.router)
    app.include_router(turnos.router)
    app.include_router(consultas.router)
    return app


app = crear_app()