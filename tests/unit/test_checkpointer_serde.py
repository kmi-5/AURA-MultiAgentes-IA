from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from backend.app.core.checkpointer import tipos_permitidos
from backend.app.data.casos_prueba import CASOS
from backend.app.models.schemas import Alerta, DatosEstructurados, SignosVitales

MODULO = "backend.app.models.schemas"


def test_la_lista_incluye_los_tipos_que_avisaba_langgraph():
    esperados = {(MODULO, n) for n in ("Alerta", "DatosEstructurados", "NivelConciencia",
                                       "AyudaDeambular", "Marcha", "EstadoMental")}
    assert esperados <= set(tipos_permitidos())


def test_los_tipos_del_estado_sobreviven_al_checkpoint():
    serde = JsonPlusSerializer(allowed_msgpack_modules=tipos_permitidos())
    alerta = Alerta(tipo_alerta="taquipnea", descripcion="Frecuencia respiratoria elevada",
                    version_reglas="1.2.0")
    datos = DatosEstructurados(paciente_id=1, turno="manana", edad=67,
                               signos_vitales=SignosVitales(**CASOS[2]["signos"]))

    for objeto in (alerta, datos):
        assert serde.loads_typed(serde.dumps_typed(objeto)) == objeto


def test_get_checkpointer_pasa_el_serializador_con_la_lista(monkeypatch):
    from backend.app.core import checkpointer as modulo

    capturado = {}

    class Falso:
        def __init__(self, pool, serde=None):
            capturado.update(pool=pool, serde=serde)

    monkeypatch.setattr(modulo, "PostgresSaver", Falso)
    monkeypatch.setattr(modulo, "get_pool", lambda: "pool-falso")

    modulo.get_checkpointer()

    assert capturado["pool"] == "pool-falso"
    assert isinstance(capturado["serde"], JsonPlusSerializer)
