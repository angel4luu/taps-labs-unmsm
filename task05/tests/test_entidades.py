import pytest

from src import entidades


@pytest.fixture(scope="module")
def ext():
    return entidades.Extractor()


def _por_tipo(detalles):
    return {d.tipo: d for d in detalles}


def test_ejemplo_completo_del_flujo_4(ext):
    d = _por_tipo(ext.extraer("Me jalaron Cálculo dos veces, ¿puedo matricularme el próximo ciclo en la FISI?"))
    assert d["curso"].valor == "Cálculo"
    assert d["veces"].valor == "2"
    assert d["facultad"].valor == "FISI"
    assert d["periodo"].valor == "proximo_ciclo"


@pytest.mark.parametrize("texto", ["Sistemas", "Soy de Ingeniería de Sistemas", "estudio en la FISI"])
def test_normaliza_sinonimos_de_facultad(ext, texto):
    assert _por_tipo(ext.extraer(texto))["facultad"].valor == "FISI"


def test_facultad_ambigua_devuelve_candidatos(ext):
    f = _por_tipo(ext.extraer("Soy de Ingeniería"))["facultad"]
    assert f.valor == "" and len(f.candidatos) >= 3 and "FISI" in f.candidatos


def test_periodo_academico(ext):
    assert _por_tipo(ext.extraer("¿cuándo es la matrícula 2026-II?"))["periodo"].valor == "2026-II"


def test_codigo_de_estudiante_se_marca_y_no_se_memoriza(ext, sesion):
    d = _por_tipo(ext.extraer("mi código es 20201234"))
    assert d["codigo_estudiante"].fuente == "regex"
    sesion.recordar(d["codigo_estudiante"])
    assert "codigo_estudiante" not in sesion.detalles_memoria


def test_lista_gana_a_spacy(ext):
    detalles = ext.extraer("Estudio en la Facultad de Ingeniería de Sistemas e Informática")
    facultades = [d for d in detalles if d.tipo == "facultad"]
    assert len(facultades) == 1 and facultades[0].fuente == "lista"
    assert not any(d.tipo == "organizacion" and "Sistemas" in d.texto for d in detalles)


def test_tipo_de_tramite_y_grado(ext):
    d = _por_tipo(ext.extraer("quiero hacer la matrícula rezagada y luego sacar mi bachiller"))
    assert d["tipo_tramite"].valor == "extemporanea" and d["grado"].valor == "bachiller"


def test_verbo_inicial_no_es_persona(ext):
    for frase in ["Desaprobé dos veces el mismo curso", "Quiero dejar de estudiar un año"]:
        assert not any(d.tipo == "persona" for d in ext.extraer(frase)), frase
