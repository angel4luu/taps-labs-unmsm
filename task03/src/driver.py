"""Apertura de Chrome controlado por ChromeDriver, siempre con la misma configuración."""
import logging
import os

from selenium import webdriver
from selenium.webdriver.chrome.service import Service

log = logging.getLogger(__name__)


def crear_driver(headless: bool = False, ruta_chromedriver: str | None = None) -> webdriver.Chrome:
    """Abre Chrome en español y maximizado.

    Por defecto Selenium Manager descarga el ChromeDriver compatible con el Chrome instalado;
    `ruta_chromedriver` permite usar un binario descargado a mano (plan B).
    """
    # En Linux la interfaz de Chrome (barra de "software automatizado") sigue a LANGUAGE, no a --lang
    os.environ["LANGUAGE"] = "es_419:es"

    opciones = webdriver.ChromeOptions()
    opciones.add_argument("--lang=es-419")
    opciones.add_argument("--start-maximized")
    opciones.add_argument("--disable-blink-features=AutomationControlled")
    opciones.add_experimental_option("prefs", {"intl.accept_languages": "es-419,es"})
    if headless:
        opciones.add_argument("--headless=new")
        opciones.add_argument("--window-size=1366,900")

    servicio = Service(executable_path=ruta_chromedriver) if ruta_chromedriver else Service()
    driver = webdriver.Chrome(service=servicio, options=opciones)
    driver.maximize_window()

    chrome, chromedriver = versiones(driver)
    log.info("Chrome %s | ChromeDriver %s", chrome, chromedriver)
    return driver


def versiones(driver: webdriver.Chrome) -> tuple[str, str]:
    """(versión de Chrome, versión de ChromeDriver) — evidencia para el PPT."""
    caps = driver.capabilities
    chromedriver = caps.get("chrome", {}).get("chromedriverVersion", "?").split(" ")[0]
    return caps.get("browserVersion", "?"), chromedriver
