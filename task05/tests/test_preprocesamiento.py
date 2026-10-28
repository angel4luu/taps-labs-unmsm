from src import preprocesamiento as pp


def test_normaliza_tildes_y_mayusculas():
    assert pp.normalizar("¿Matrícula REZAGADA?") == "matricula rezagada"


def test_conserva_enie():
    assert pp.normalizar("Año académico") == "año academico"


def test_quita_stopwords_pero_conserva_interrogativas():
    tokens = pp.quitar_stopwords(pp.tokenizar(pp.normalizar("cuándo es la matrícula de los cursos")))
    assert "la" not in tokens and "de" not in tokens
    assert "cuando" in tokens


def test_misma_raiz_para_variantes():
    raices = {pp.raices(p)[0] for p in ["matriculé", "matricularme", "matrícula"]}
    assert len(raices) == 1


def test_trunca_a_mil_caracteres():
    assert len(pp.procesar("a" * 1500).texto_original) == 1000


def test_pasos_devuelve_cinco_pasos():
    pasos = pp.pasos("¿Hasta cuándo es la matrícula rezagada?")
    assert len(pasos) == 5
    assert all(isinstance(nombre, str) for nombre, _ in pasos)
