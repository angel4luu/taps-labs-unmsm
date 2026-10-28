import pytest

from src import politica
from src.modelos import Componente, Detalle, Politica, ResultadoIntencion, Sesion
from src.orquestador import Orquestador


def _resultado(intencion, confianza, segunda="matricula", conf2=0.1):
    return ResultadoIntencion(intencion=intencion, confianza=confianza, top2=[(intencion, confianza), (segunda, conf2)],
                              modelo="prueba", banda="")


@pytest.fixture(scope="module")
def definiciones():
    return politica.cargar_definiciones()


def test_banda_aceptar(definiciones):
    d = politica.decidir(_resultado("repitencia", 0.9), [], Sesion(), definiciones, 0.6, 0.35)
    assert d.banda == "aceptar" and d.filtro_tema == "repitencia"


def test_banda_confirmar(definiciones):
    d = politica.decidir(_resultado("repitencia", 0.45, "matricula", 0.4), [], Sesion(), definiciones, 0.6, 0.35)
    assert d.banda == "confirmar" and "repitencia" in d.pregunta.lower() and "matrícula" in d.pregunta.lower()


def test_banda_sin_filtro(definiciones):
    d = politica.decidir(_resultado("tramites", 0.2), [], Sesion(), definiciones, 0.6, 0.35)
    assert d.banda == "sin_filtro" and d.filtro_tema is None


def test_detalle_requerido_faltante(definiciones):
    d = politica.decidir(_resultado("calendario", 0.9), [], Sesion(), definiciones, 0.6, 0.35)
    assert d.faltante == "facultad" and "facultad" in d.pregunta.lower()


def test_detalle_en_memoria_no_se_vuelve_a_pedir(definiciones):
    s = Sesion()
    s.recordar(Detalle(tipo="facultad", valor="FISI", texto="FISI", fuente="lista"))
    d = politica.decidir(_resultado("calendario", 0.9), [], s, definiciones, 0.6, 0.35)
    assert d.faltante is None and d.uso_memoria


# --- escenarios completos con el orquestador (LLM reemplazado por un stub) -----------------------
@pytest.fixture
def orq(config, stub_llm):
    o = Orquestador.cargar(config)
    o.config.UMBRAL_ACEPTAR, o.config.UMBRAL_RECHAZAR = 0.6, 0.35
    return o


def test_pide_facultad_y_luego_completa_la_pregunta(orq):
    s = orq.nueva_sesion()
    r1 = orq.responder("¿Hasta cuándo es la matrícula?", s)
    assert Politica.PEDIR_DETALLE in r1.politica and "facultad" in r1.texto.lower()
    r2 = orq.responder("Sistemas", s)
    assert Politica.MEMORIA_SESION in r2.politica
    assert "Ingeniería de Sistemas" in r2.texto
    assert any(f.ubicacion.startswith("Art. 5") for f in r2.fuentes)
    # SC-005: la facultad no se vuelve a pedir
    r3 = orq.responder("¿cuándo empieza la matrícula?", s)
    assert Politica.PEDIR_DETALLE not in r3.politica


def test_respuesta_sin_el_detalle_se_pide_una_vez_mas_y_luego_general(orq):
    s = orq.nueva_sesion()
    orq.responder("¿Hasta cuándo es la matrícula?", s)
    r2 = orq.responder("no sé", s)
    assert Politica.PEDIR_DETALLE in r2.politica
    r3 = orq.responder("ni idea", s)
    assert Politica.PEDIR_DETALLE not in r3.politica and "general" in r3.texto.lower()


def test_confirmacion_se_resuelve_con_el_tema(orq, monkeypatch):
    s = orq.nueva_sesion()
    original = orq.modelo.predecir
    monkeypatch.setattr(orq.modelo, "predecir",
                        lambda m: _con_banda(_resultado("repitencia", 0.45, "creditos_cursos", 0.4))
                        if "problema" in m.texto_normalizado else original(m))
    r1 = orq.responder("tengo un problema con mi curso", s)
    assert Politica.CONFIRMAR_TOP2 in r1.politica
    r2 = orq.responder("repitencia", s)
    assert r2.intencion.intencion == "repitencia" and Politica.CONFIRMAR_TOP2 not in r2.politica


def test_fuera_de_dominio_no_llama_al_llm(orq, stub_llm):
    r = orq.responder("¿quién ganó el clásico de ayer?", orq.nueva_sesion())
    assert Politica.FUERA_DOMINIO in r.politica and r.componente == Componente.NLP_ML
    assert stub_llm == []


def _con_banda(resultado):
    return resultado


def test_confirmacion_nunca_ofrece_fuera_de_dominio(definiciones):
    r = ResultadoIntencion("fuera_de_dominio", 0.4, [("fuera_de_dominio", 0.4), ("bienestar", 0.3),
                                                     ("repitencia", 0.2)], "prueba", "")
    d = politica.decidir(r, [], Sesion(), definiciones, 0.6, 0.35)
    assert d.banda == "confirmar" and d.opciones == ["bienestar", "repitencia"]
