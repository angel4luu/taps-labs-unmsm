import pytest

from src import evaluacion
from src.orquestador import Orquestador


@pytest.fixture(scope="module")
def orq():
    return Orquestador.cargar()


def test_sc003_recuperacion_con_intencion(orq):
    """SC-003 con el pipeline real: intención → banda → recuperación filtrada por tema.
    En la banda «confirmar» se simula que el estudiante elige su tema si está entre los dos ofrecidos."""
    m = evaluacion.recuperacion_con_intencion(orq, orq.config.ruta("evaluacion", "preguntas_retrieval.csv"))
    assert m["n_con_respuesta"] >= 30 and m["n_sin_respuesta"] >= 10
    assert m["hit_at_1"] >= 0.80, m["hit_at_1"]
    assert m["no_respuesta_correcta"] >= 0.90, m["no_respuesta_correcta"]
