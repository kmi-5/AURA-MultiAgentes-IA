import json

import httpx
import pytest

import api_client as api


def cliente(handler, token="tok-secreto"):
    return api.ApiClient("http://api.test", token, timeout=5, transport=httpx.MockTransport(handler))


def test_login_json_devuelve_token():
    def h(req):
        assert req.url.path == api.RUTAS["login"]
        assert json.loads(req.content) == {"username": "enf", "password": "pw"}
        return httpx.Response(200, json={"access_token": "abc"})
    assert cliente(h, None).login("enf", "pw")["access_token"] == "abc"


def test_login_incorrecto_es_401():
    c = cliente(lambda r: httpx.Response(401, json={"detail": "Credenciales inválidas"}), None)
    with pytest.raises(api.NoAutenticado):
        c.login("x", "y")


def test_procesar_envia_idempotency_key_y_bearer():
    visto = {}
    def h(req):
        visto.update(req.headers)
        return httpx.Response(200, json={"thread_id": "7:manana:2026-10-28"})
    r = cliente(h).procesar({"paciente_id": 1}, "clave-123")
    assert visto["idempotency-key"] == "clave-123"
    assert visto["authorization"] == "Bearer tok-secreto"
    assert api.extraer_thread_id(r) == "7:manana:2026-10-28"


def test_422_se_mapea_por_campo():
    detalle = [{"loc": ["body", "signos_vitales", "fc"], "msg": "Input should be >= 20", "type": "x"},
               {"loc": ["body", "observacion"], "msg": "Value error, texto no permitido", "type": "y"}]
    c = cliente(lambda r: httpx.Response(422, json={"detail": detalle}))
    with pytest.raises(api.Validacion) as e:
        c.procesar({}, "k")
    assert e.value.campos == {"signos_vitales.fc": "Input should be >= 20", "observacion": "texto no permitido"}


@pytest.mark.parametrize("status,clase", [(403, api.Prohibido), (404, api.NoEncontrado), (409, api.Conflicto),
                                          (429, api.LimiteExcedido), (503, api.ServicioNoDisponible),
                                          (500, api.ServicioNoDisponible)])
def test_codigos_de_error(status, clase):
    c = cliente(lambda r: httpx.Response(status, json={"detail": "x"}))
    with pytest.raises(clase):
        c.decidir("t", "aprobado", "clave-1234")


def test_timeout_y_conexion_son_error_de_conexion():
    def h(req):
        raise httpx.ConnectTimeout("lento")
    with pytest.raises(api.ErrorConexion):
        cliente(h).listar_pacientes()
    def h2(req):
        raise httpx.ConnectError("caída")
    with pytest.raises(api.ErrorConexion):
        cliente(h2).listar_pacientes()


def test_el_token_no_aparece_en_los_errores():
    c = cliente(lambda r: httpx.Response(500, text="boom"), token="tok-secreto")
    with pytest.raises(api.ServicioNoDisponible) as e:
        c.pase(1)
    assert "tok-secreto" not in str(e.value) and "tok-secreto" not in repr(e.value.detalle)


def test_decidir_manda_evolucion_y_idempotency_key():
    cuerpo, headers = {}, {}
    def h(req):
        cuerpo.update(json.loads(req.content)); headers.update(req.headers)
        assert req.url.path == "/turnos/t1/decision"
        return httpx.Response(200, json={})
    cliente(h).decidir("t1", "editado", "clave-de-decision", "texto nuevo")
    assert cuerpo == {"decision": "editado", "evolucion_editada": "texto nuevo"}
    assert headers["idempotency-key"] == "clave-de-decision"


def test_rutas_por_paciente_y_filtros():
    vistos = []
    def h(req):
        vistos.append((req.url.path, dict(req.url.params)))
        return httpx.Response(200, json=[])
    c = cliente(h)
    c.tareas(7, estado="pendiente"); c.alertas(7); c.auditoria(500); c.listar_pacientes()
    assert vistos == [("/pacientes/7/tareas", {"estado": "pendiente"}), ("/pacientes/7/alertas", {}),
                      ("/auditoria", {"limit": "200"}), ("/pacientes", {"limit": "200"})]


def test_pase_sin_datos_es_404():
    with pytest.raises(api.NoEncontrado):
        cliente(lambda r: httpx.Response(404, json={"detail": "Sin pase"})).pase(1)


def test_422_de_idempotencia_conserva_el_mensaje():
    c = cliente(lambda r: httpx.Response(422, json={"detail": "La clave de idempotencia ya se usó con otro contenido"}))
    with pytest.raises(api.Validacion) as e:
        c.procesar({}, "k" * 8)
    assert "otro contenido" in e.value.mensaje and e.value.campos == {}


def test_consultar_turno():
    c = cliente(lambda r: httpx.Response(200, json={"thread_id": "x", "estado": "completado"}))
    assert c.consultar_turno("x")["estado"] == "completado"


def test_listas_toleran_lista_o_items():
    assert api.como_lista([1]) == [1]
    assert api.como_lista({"items": [2]}) == [2]
    assert api.como_lista({"x": 1}) == []

