"""Capturas de las transcripciones de los flujos (HTML generado por el mismo renderer del widget)."""

from __future__ import annotations

from pathlib import Path

from src.config import DIR_CAPTURAS

ANCHO = 560  # angosto: en una columna de la diapositiva el texto queda legible
ALTO_MAXIMO = 680  # partes más bajas: van en columnas, una al lado de la otra


def capturar(paginas: list[Path], destino: Path = DIR_CAPTURAS) -> list[Path]:
    """Captura cada transcripción; si es muy alta, la parte en grupos de turnos completos."""
    from playwright.sync_api import sync_playwright

    destino.mkdir(parents=True, exist_ok=True)
    generadas = []
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page(viewport={"width": ANCHO, "height": 800}, device_scale_factor=2)
        for html in paginas:
            pagina.goto(html.resolve().as_uri())
            filas = pagina.locator(".chat-unmsm .fila")
            cajas = [filas.nth(i).bounding_box() for i in range(filas.count())]
            contenedor = pagina.locator(".chat-unmsm").bounding_box()
            grupos, actual = [], []
            for i in range(0, len(cajas), 2):  # pares usuario + bot
                par = cajas[i:i + 2]
                alto = (par[-1]["y"] + par[-1]["height"]) - (actual[0]["y"] if actual else par[0]["y"])
                if actual and alto > ALTO_MAXIMO:
                    grupos.append(actual)
                    actual = []
                actual += par
            if actual:
                grupos.append(actual)
            for k, grupo in enumerate(grupos, start=1):
                y0 = (contenedor["y"] if k == 1 else grupo[0]["y"] - 8)
                y1 = grupo[-1]["y"] + grupo[-1]["height"] + 12
                salida = destino / f"{html.stem}_{k}.png"
                pagina.screenshot(path=str(salida), full_page=True,
                                  clip={"x": contenedor["x"], "y": y0, "width": contenedor["width"], "height": y1 - y0})
                generadas.append(salida)
        navegador.close()
    return generadas
