"""Pruebas de src/parser.py con textos reales observados en la Fase 1.

Ejecutar desde task03/:  python -m tests.test_parser
"""
from src.parser import generar_id, limpiar_texto, parsear_estrellas, parsear_fecha, parsear_votos


def test_estrellas():
    assert parsear_estrellas("Calificación: 1 de cinco estrellas") == 1
    assert parsear_estrellas("Calificación: 5 de cinco estrellas") == 5
    assert parsear_estrellas(None) is None


def test_fecha():
    assert parsear_fecha("18 de septiembre de 2026") == "2026-09-18"
    assert parsear_fecha("7 de octubre de 2026") == "2026-10-07"
    assert parsear_fecha("3 de setiembre de 2026") == "2026-09-03"
    assert parsear_fecha("texto sin fecha") is None


def test_votos():
    assert parsear_votos("Esta opinión les resultó útil a 6 personas") == 6
    assert parsear_votos("Esta opinión le resultó útil a 1 persona") == 1
    assert parsear_votos("Esta opinión les resultó útil a 1.234 personas") == 1234
    assert parsear_votos(None) == 0


def test_limpiar_e_id():
    assert limpiar_texto("  muy   buena\napp ") == "muy buena app"
    assert limpiar_texto("pésimo​ servicio 👎") == "pésimo servicio 👎"
    a = generar_id("Rumi", "2026-09-18", "texto")
    assert a == generar_id("Rumi", "2026-09-18", "texto") and len(a) == 40
    assert a != generar_id("Rumi", "2026-09-19", "texto")


if __name__ == "__main__":
    pruebas = [f for n, f in dict(globals()).items() if n.startswith("test_")]
    for prueba in pruebas:
        prueba()
        print("OK ", prueba.__name__)
    print(f"{len(pruebas)} pruebas superadas")
