"""Único lugar que habla HTTP con la API. No importa nada de backend.app.

Contrato tomado de backend/app/routers (auth, turnos, consultas, esquemas). Si la API cambia,
se ajusta ACÁ y solo acá (RUTAS, DECISIONES y los métodos de ApiClient).
"""
from __future__ import annotations

import httpx

RUTAS = {
    "login": "/auth/login",
    "pacientes": "/pacientes",
    "procesar": "/turnos/procesar",
    "turno": "/turnos/{thread_id}",
    "decision": "/turnos/{thread_id}/decision",
    "pase": "/pacientes/{paciente_id}/pase",
    "tareas": "/pacientes/{paciente_id}/tareas",
    "alertas": "/pacientes/{paciente_id}/alertas",
    "auditoria": "/auditoria",
}
# Valores de `decision` que acepta DecisionHumana (backend/app/graph/aprobacion.py). CONFIRMAR "aprobado"/"editado".
DECISIONES = ("aprobado", "editado", "descartado")


# ---------------------------------------------------------------- errores propios
class ErrorApi(Exception):
    def __init__(self, mensaje: str, status: int | None = None, detalle=None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status = status
        self.detalle = detalle


class NoAutenticado(ErrorApi):      # 401
    pass


class Prohibido(ErrorApi):          # 403
    pass


class NoEncontrado(ErrorApi):       # 404
    pass


class Conflicto(ErrorApi):          # 409
    pass


class LimiteExcedido(ErrorApi):     # 429
    pass


class Validacion(ErrorApi):         # 422
    def __init__(self, mensaje, status=422, detalle=None, campos=None):
        super().__init__(mensaje, status, detalle)
        self.campos = campos or {}


class ServicioNoDisponible(ErrorApi):  # 503 y otros 5xx
    pass


class ErrorConexion(ErrorApi):      # timeout, DNS, conexión rechazada
    pass


# ---------------------------------------------------------------- helpers de contrato
def campos_de_422(detalle) -> dict[str, str]:
    """Convierte el `detail` de un 422 de FastAPI en {'signos_vitales.fc': 'mensaje'}."""
    campos: dict[str, str] = {}
    if not isinstance(detalle, list):
        return campos
    for item in detalle:
        if not isinstance(item, dict):
            continue
        loc = [str(p) for p in item.get("loc", []) if p not in ("body", "query")]
        clave = ".".join(loc) or "_general"
        msg = str(item.get("msg", "valor inválido"))
        msg = msg.removeprefix("Value error, ")
        campos.setdefault(clave, msg)
    return campos


def extraer_thread_id(resp: dict) -> str | None:
    return str(resp["thread_id"]) if resp.get("thread_id") else None


def como_lista(resp) -> list:
    """Acepta una lista directa o un objeto {'items': [...]} / {'resultados': [...]}."""
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for k in ("items", "resultados", "data"):
            if isinstance(resp.get(k), list):
                return resp[k]
    return []


# ---------------------------------------------------------------- cliente
class ApiClient:
    def __init__(self, base_url: str, token: str | None = None, timeout: float = 120.0,
                 transport: httpx.BaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._transport = transport

    # -- núcleo
    def _pedir(self, metodo: str, ruta: str, *, json=None, data=None, params=None,
               headers: dict | None = None):
        h = {"Accept": "application/json", **(headers or {})}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout,
                              transport=self._transport) as c:
                r = c.request(metodo, ruta, json=json, data=data, params=params, headers=h)
        except httpx.TimeoutException:
            raise ErrorConexion("La API no respondió a tiempo.") from None
        except httpx.TransportError:
            raise ErrorConexion("No se pudo conectar con la API.") from None
        if r.status_code >= 400:
            self._levantar(r)
        if not r.content:
            return {}
        try:
            return r.json()
        except ValueError:
            raise ErrorApi("La API devolvió una respuesta que no es JSON.", r.status_code) from None

    @staticmethod
    def _levantar(r: httpx.Response):
        try:
            detalle = r.json().get("detail")
        except Exception:
            detalle = None
        texto = detalle if isinstance(detalle, str) else (r.reason_phrase or "Error")
        s = r.status_code
        if s == 401:
            raise NoAutenticado(texto, s, detalle)
        if s == 403:
            raise Prohibido(texto, s, detalle)
        if s == 404:
            raise NoEncontrado(texto, s, detalle)
        if s == 409:
            raise Conflicto(texto, s, detalle)
        if s == 422:
            msg = detalle if isinstance(detalle, str) else "Hay datos inválidos."
            raise Validacion(msg, s, detalle, campos_de_422(detalle))
        if s == 429:
            raise LimiteExcedido("Demasiados intentos. Esperá un momento.", s, detalle)
        if s >= 500:
            raise ServicioNoDisponible("El servicio no está disponible o falló.", s, detalle)
        raise ErrorApi(texto, s, detalle)

    # -- endpoints
    def login(self, usuario: str, password: str) -> dict:
        return self._pedir("POST", RUTAS["login"], json={"username": usuario, "password": password})

    def listar_pacientes(self) -> list:
        return como_lista(self._pedir("GET", RUTAS["pacientes"], params={"limit": 200}))

    def procesar(self, payload: dict, clave_idempotencia: str) -> dict:
        return self._pedir("POST", RUTAS["procesar"], json=payload,
                           headers={"Idempotency-Key": clave_idempotencia})

    def consultar_turno(self, thread_id: str) -> dict:
        return self._pedir("GET", RUTAS["turno"].format(thread_id=thread_id))

    def decidir(self, thread_id: str, decision: str, clave_idempotencia: str,
                evolucion_editada: str | None = None, motivo: str | None = None) -> dict:
        cuerpo = {"decision": decision}
        if evolucion_editada is not None:
            cuerpo["evolucion_editada"] = evolucion_editada
        if motivo:
            cuerpo["motivo"] = motivo
        return self._pedir("POST", RUTAS["decision"].format(thread_id=thread_id), json=cuerpo,
                           headers={"Idempotency-Key": clave_idempotencia})

    def pase(self, paciente_id: int) -> dict:
        """Último pase del paciente. Levanta NoEncontrado si todavía no hay ninguno."""
        return self._pedir("GET", RUTAS["pase"].format(paciente_id=paciente_id))

    def tareas(self, paciente_id: int, estado: str | None = None) -> list:
        return como_lista(self._pedir("GET", RUTAS["tareas"].format(paciente_id=paciente_id),
                                      params={"estado": estado} if estado else None))

    def alertas(self, paciente_id: int) -> list:
        return como_lista(self._pedir("GET", RUTAS["alertas"].format(paciente_id=paciente_id)))

    def auditoria(self, limite: int = 100) -> list:
        return como_lista(self._pedir("GET", RUTAS["auditoria"], params={"limit": min(limite, 200)}))
