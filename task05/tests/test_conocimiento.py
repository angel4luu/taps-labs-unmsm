from src import conocimiento
from src.modelos import EntradaConocimiento

FUENTE = {"id": "doc", "documento": "Reglamento de prueba", "url": "https://ejemplo.pe/r.pdf",
          "fecha_fuente": "2026-02-25", "oficina": "Unidad de prueba"}

RELLENO = "texto de relleno para que el artículo tenga longitud suficiente en la prueba unitaria " * 2


def _texto(*articulos: str) -> str:
    return "REGLAMENTO GENERAL DE MATRÍCULA PARA PREGRADO\nTITULO I: GENERALIDADES\n" + "\n".join(articulos)


def test_divide_por_articulo_con_ubicacion():
    texto = _texto(f"Artículo 10° La matrícula es el acto formal. {RELLENO}",
                   f"Artículo 11° La matrícula se clasifica en tres tipos. {RELLENO}",
                   f"Artículo 12° La matrícula en una asignatura desaprobada. {RELLENO}")
    pasajes = conocimiento.dividir_articulos(texto, FUENTE)
    assert [p.ubicacion for p in pasajes] == ["Art. 10", "Art. 11", "Art. 12"]
    assert all(p.documento and p.url and p.fecha_fuente for p in pasajes)
    assert pasajes[2].tema == "repitencia"


def test_articulo_largo_se_parte_por_incisos_conservando_el_id():
    incisos = " ".join(f"\n{letra}) " + "palabra " * 60 for letra in "abcdefg")
    pasajes = conocimiento.dividir_articulos(_texto(f"Artículo 12° Encabezado del artículo. {incisos}"), FUENTE)
    assert len(pasajes) > 1
    assert all(p.id.startswith("doc-art-12") for p in pasajes)
    assert all(len(p.texto.split()) <= conocimiento.MAX_PALABRAS_PASAJE for p in pasajes)


def test_articulo_corto_se_une_al_siguiente():
    pasajes = conocimiento.dividir_articulos(
        _texto("Artículo 34° El proceso culmina según el cronograma.", f"Artículo 35° Terminado el proceso. {RELLENO}"),
        FUENTE)
    assert len(pasajes) == 1 and pasajes[0].ubicacion == "Arts. 34–35"


def test_validacion_rechaza_longitud_y_tema_invalidos():
    base = dict(tipo="pasaje", documento="d", ubicacion="Art. 1", fecha_fuente="2026-01-01")
    corto = EntradaConocimiento(id="a", tema="matricula", texto="muy corto", **base)
    tema_malo = EntradaConocimiento(id="b", tema="deportes", texto="palabra " * 30, **base)
    errores = conocimiento.validar([corto, tema_malo])
    assert any("palabras" in e for e in errores) and any("tema" in e for e in errores)


def test_pasajes_reales_son_validos(config):
    pasajes = conocimiento.cargar_jsonl(config.ruta("conocimiento", "pasajes.jsonl"))
    assert len(pasajes) >= 37
    assert conocimiento.validar(pasajes) == []
    assert any(p.id == "matricula-2026-art-12" for p in pasajes)
