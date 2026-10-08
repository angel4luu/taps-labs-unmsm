"""Fase 0 - Prueba rápida: Python -> Selenium -> ChromeDriver -> Chrome -> Google Play."""
from src.config import DIR_CAPTURAS, URL
from src.driver import crear_driver, versiones
from src.evidencia import capturar_pantalla

driver = crear_driver()  # Selenium Manager resuelve el ChromeDriver compatible
try:
    driver.get(URL)
    chrome, chromedriver = versiones(driver)
    print("Título:", driver.title)
    print("Chrome:", chrome)
    print("ChromeDriver:", chromedriver)
    print("Captura guardada en:", capturar_pantalla(driver, DIR_CAPTURAS / "00_prueba_rapida.png"))
finally:
    driver.quit()
