import pytest

from backend.app.agents.enfermeria import crear_nodo_enfermeria
from backend.app.agents.seguridad import crear_nodo_seguridad
from backend.app.data.casos_prueba import entrada_de


@pytest.fixture
def armar_estado():
    """Fábrica de TurnoState listos para los nodos finales (consolidar, persistencia)."""
    def _armar(caso, decision="aprobado", **cambios):
        obtener_edad = lambda _pid: caso["edad"]
        estado = {"paciente_id": 1, "turno": "manana", "usuario_id": 1,
                  "idempotency_key": "clave-1"}
        estado.update(crear_nodo_enfermeria(obtener_edad=obtener_edad)(
            {"entrada_cruda": entrada_de(caso, 1)}))
        seguridad = crear_nodo_seguridad(obtener_edad=obtener_edad)(estado)
        estado.update({k: v for k, v in seguridad.items() if k != "estado_nodos"})
        estado.update(
            estado_nodos={"enfermeria": "ok", "seguridad": "ok", "documentacion": "ok"},
            evolucion="Evolución de prueba.", pase_guardia="Pase de prueba.",
            decision_humana=decision,
            requiere_revision=bool(caso["alertas_esperadas"]), turno_incompleto=False,
        )
        estado.update(cambios)
        return estado
    return _armar
