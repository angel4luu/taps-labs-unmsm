import pytest

from src import recuperacion
from src.modelos import Componente


@pytest.fixture(scope="module")
def indice():
    return recuperacion.Indice.desde_archivos()


def test_faq_de_reserva_se_devuelve_textualmente(indice):
    r = indice.respuesta_directa("¿Cómo hago la reserva de matrícula?", None)
    faq = next(e for e in indice.entradas if e.id == "faq-007")
    assert r.componente == Componente.RETRIEVAL
    assert r.texto.startswith(faq.texto)  # FR-020: se devuelve textualmente
    assert r.fuentes[0].id == "faq-007" and r.fuentes[0].score is not None


def test_parafrasis_sigue_coincidiendo(indice):
    r = indice.respuesta_directa("cómo solicito la reserva de mi matrícula", None)
    assert r is not None and r.fuentes[0].id == "faq-007"


def test_pregunta_sin_entrada_no_se_responde(indice):
    assert indice.respuesta_directa("¿Cuál es la capital de Francia?", None) is None


def test_filtro_por_tema(indice):
    resultados = indice.buscar("matrícula de un curso desaprobado", tema="repitencia", k=5)
    assert resultados and all(e.tema == "repitencia" for e, _ in resultados)


def test_contexto_devuelve_pasajes_del_reglamento(indice):
    pasajes = indice.contexto("desaprobé dos veces la misma asignatura", "repitencia")
    assert pasajes and all(p.tipo == "pasaje" for p in pasajes)
    assert any("Art. 12" in p.ubicacion or "Art. 13" in p.ubicacion for p in pasajes)


def test_recordatorio_en_fuentes_referenciales(indice):
    r = indice.respuesta_directa("como entro al comedor de la universidad", None)
    assert r is not None and r.recordatorio_referencial


def test_metricas_componente_aislado(indice, config):
    """Recuperación sola (sin filtro de intención), en el conjunto de prueba no usado para ajustar.

    SC-003 (acierto ≥ 0.80 y no-respuesta ≥ 0.90) se mide con el pipeline completo en test_pipeline.py,
    porque FR-019 filtra por la intención antes de recuperar.
    """
    m = indice.evaluar(config.ruta("evaluacion", "preguntas_retrieval.csv"))
    assert m["n_con_respuesta"] >= 30 and m["n_sin_respuesta"] >= 10
    assert m["hit_at_3"] >= 0.85, m
