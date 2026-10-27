from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from backend.app.data.casos_prueba import CASOS, entrada_de
from backend.app.models.db_models import AlertaSeguridad, Auditoria, PaseTurno

CASO = next(c for c in CASOS if c["escenario"] == "hipertermia_taquicardia_y_taquipnea")
EDITADA = "Evolución corregida por la enfermera."


def _procesar(client, auth_headers, clave="clave-proc-0001", paciente=1) -> str:
    r = client.post("/turnos/procesar", json=entrada_de(CASO, paciente),
                    headers=auth_headers("enfermeria", clave))
    assert r.status_code == 200, r.text
    return r.json()["thread_id"]


def _decidir(client, auth_headers, tid, cuerpo, clave="clave-dec-00001", rol="enfermeria"):
    return client.post(f"/turnos/{tid}/decision", json=cuerpo, headers=auth_headers(rol, clave))


def _n(sf, modelo) -> int:
    with sf() as db:
        return db.scalar(select(func.count()).select_from(modelo))


def _tareas_auditadas(sf) -> set[str]:
    with sf() as db:
        return set(db.scalars(select(Auditoria.tarea)).all())


def test_aprobar_guarda_el_turno_y_audita_ambos_rastros(client, session_factory, auth_headers):
    tid = _procesar(client, auth_headers)
    r = _decidir(client, auth_headers, tid, {"decision": "aprobado"})
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "completado"
    assert _n(session_factory, PaseTurno) == 1
    assert _n(session_factory, AlertaSeguridad) == len(CASO["alertas_esperadas"])
    assert {"turno_aprobado", "decision_turno"} <= _tareas_auditadas(session_factory)


def test_repetir_la_decision_con_la_misma_clave_no_duplica(client, session_factory, auth_headers):
    tid = _procesar(client, auth_headers)
    a = _decidir(client, auth_headers, tid, {"decision": "aprobado"}, "clave-dec-repe01")
    b = _decidir(client, auth_headers, tid, {"decision": "aprobado"}, "clave-dec-repe01")
    assert a.status_code == b.status_code == 200
    assert b.headers["Idempotent-Replay"] == "true"
    assert _n(session_factory, PaseTurno) == 1


def test_decidir_dos_veces_con_claves_distintas_da_409(client, session_factory, auth_headers):
    tid = _procesar(client, auth_headers)
    assert _decidir(client, auth_headers, tid, {"decision": "aprobado"}, "clave-dec-aaaa1").status_code == 200
    assert _decidir(client, auth_headers, tid, {"decision": "descartado"}, "clave-dec-bbbb1").status_code == 409
    assert _n(session_factory, PaseTurno) == 1


def test_editar_guarda_la_evolucion_de_la_enfermera(client, session_factory, auth_headers):
    tid = _procesar(client, auth_headers)
    r = _decidir(client, auth_headers, tid, {"decision": "editado", "evolucion_editada": EDITADA})
    assert r.status_code == 200 and r.json()["estado"] == "completado"
    with session_factory() as db:
        assert EDITADA in db.scalar(select(PaseTurno.contenido_consolidado))


def test_descartar_no_guarda_nada_clinico_pero_audita(client, session_factory, auth_headers):
    tid = _procesar(client, auth_headers)
    r = _decidir(client, auth_headers, tid, {"decision": "descartado", "motivo": "datos cargados al paciente equivocado"})
    assert r.status_code == 200 and r.json()["estado"] == "descartado"
    assert _n(session_factory, PaseTurno) == 0
    assert _n(session_factory, AlertaSeguridad) == 0
    assert {"turno_descartado", "decision_turno"} <= _tareas_auditadas(session_factory)


def test_editar_sin_texto_da_422(client, auth_headers):
    tid = _procesar(client, auth_headers)
    assert _decidir(client, auth_headers, tid, {"decision": "editado"}).status_code == 422


def test_campo_desconocido_da_422(client, auth_headers):
    tid = _procesar(client, auth_headers)
    assert _decidir(client, auth_headers, tid, {"decision": "aprobado", "extra": 1}).status_code == 422


def test_turno_inexistente_da_404(client, auth_headers):
    assert _decidir(client, auth_headers, "999:manana:2026-01-01", {"decision": "aprobado"}).status_code == 404


def test_rol_auditoria_no_puede_decidir(client, auth_headers):
    tid = _procesar(client, auth_headers)
    assert _decidir(client, auth_headers, tid, {"decision": "aprobado"}, rol="auditoria").status_code == 403


def test_supervision_puede_decidir(client, auth_headers):
    tid = _procesar(client, auth_headers)
    assert _decidir(client, auth_headers, tid, {"decision": "aprobado"}, rol="supervision").status_code == 200


def test_el_pase_se_acumula_en_un_segundo_procesamiento_tras_aprobar(client, session_factory, auth_headers):
    tid = _procesar(client, auth_headers, "clave-proc-ciclo1")
    _decidir(client, auth_headers, tid, {"decision": "aprobado"}, "clave-dec-ciclo01")
    tid2 = _procesar(client, auth_headers, "clave-proc-ciclo2")
    assert tid2 == tid                                   # mismo paciente-turno-día: mismo hilo
    _decidir(client, auth_headers, tid2, {"decision": "aprobado"}, "clave-dec-ciclo02")
    assert _n(session_factory, PaseTurno) == 2           # dos guardados, claves distintas, sin choque


class FabricaInestable:
    """Falla la primera vez que abre una transacción: una caída momentánea de la base."""
    def __init__(self, real):
        self.real, self.fallos = real, 1

    def begin(self):
        if self.fallos:
            self.fallos -= 1
            raise OperationalError("INSERT", {}, Exception("base no disponible"))
        return self.real.begin()


def test_persistencia_caida_da_503_y_el_reintento_completa_sin_duplicar(
        session_factory, grafo_de, make_client, auth_headers):
    cliente = make_client(grafo_de(FabricaInestable(session_factory)))
    ah = lambda rol, clave: auth_headers(rol, clave, cliente=cliente)          # noqa: E731
    r = cliente.post("/turnos/procesar", json=entrada_de(CASO, 1), headers=ah("enfermeria", "clave-pers-proc1"))
    tid = r.json()["thread_id"]

    caida = cliente.post(f"/turnos/{tid}/decision", json={"decision": "aprobado"}, headers=ah("enfermeria", "clave-pers-dec01"))
    assert caida.status_code == 503
    assert _n(session_factory, PaseTurno) == 0
    assert cliente.get(f"/turnos/{tid}", headers=ah("enfermeria", "clave-pers-get01")).json()["estado"] == "persistencia_pendiente"

    # mientras el guardado está a medias no se puede abrir otro procesamiento del mismo paciente-turno
    assert cliente.post("/turnos/procesar", json=entrada_de(CASO, 1), headers=ah("enfermeria", "clave-pers-proc2")).status_code == 409

    ok = cliente.post(f"/turnos/{tid}/decision", json={"decision": "aprobado"}, headers=ah("enfermeria", "clave-pers-dec02"))
    assert ok.status_code == 200 and ok.json()["estado"] == "completado"
    assert _n(session_factory, PaseTurno) == 1
