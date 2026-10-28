import re

import pytest

from src import flujos
from src.interfaz import render_html
from src.modelos import Componente, Politica
from src.orquestador import Orquestador


@pytest.fixture
def resultados(config, stub_llm):
    orq = Orquestador.cargar(config)
    return orq, flujos.ejecutar_todos(orq, tipo=None)


def test_cuatro_casos_de_uso_y_escenas(config):
    assert [f["id"] for f in flujos.cargar(config, "caso")] == [1, 2, 3, 4]
    assert {f["id"] for f in flujos.cargar(config, "escena")} == {"reglas", "recuperacion", "nlp", "llm",
                                                                  "llm_offline"}


def test_todas_las_conversaciones_se_comportan_como_se_espera(resultados):
    orq, res = resultados
    errores = [e for id_, turnos in res.items() for e in flujos.verificar(id_, turnos, orq.config, en_linea=True)]
    assert errores == []


def test_cubren_todos_los_componentes_y_politicas(resultados):
    """SC-008: los 4 componentes, el modo sin conexión y todas las políticas aparecen en la presentación."""
    _, res = resultados
    respuestas = [r for turnos in res.values() for _, r in turnos]
    componentes = {r.componente for r in respuestas}
    assert {Componente.REGLAS, Componente.NLP_ML, Componente.RETRIEVAL, Componente.LLM} <= componentes
    assert componentes & {Componente.LLM_LOCAL, Componente.FALLBACK_EXTRACTIVO}
    politicas = {p for r in respuestas for p in r.politica}
    assert set(Politica) - {Politica.NINGUNA} <= politicas


def test_cada_caso_de_uso_recorre_varios_componentes(resultados):
    _, res = resultados
    for id_ in (1, 3, 4):
        assert len({r.componente for _, r in res[id_]}) >= 2, id_


def test_html_tiene_una_insignia_por_turno_y_ninguna_clave(resultados, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza" + "0" * 12)  # falsa y más corta que una clave real
    _, res = resultados
    for turnos in res.values():
        contenido = render_html(turnos)
        assert contenido.count('class="badge"') == len(turnos)
        assert "GEMINI_API_KEY" not in contenido and not re.search(r"AIza[0-9A-Za-z_\-]{10,}", contenido)


def test_traza_para_diapositivas(resultados):
    _, res = resultados
    filas = flujos.traza(res[1])
    assert filas[1]["Política"] == "Pide detalle" and "facultad=FISI" in filas[2]["Señal clave"]
