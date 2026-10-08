"""Navegación con Selenium: abrir el modal, ordenar, hacer scroll y extraer reseñas.

Uso desde la terminal (con el entorno task03 activado):
    python -m src.scraper --meta 1050
"""
import argparse
import logging
import random
import time
from datetime import datetime

from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from tqdm.auto import tqdm

from src import config as cfg
from src.driver import crear_driver, versiones
from src.evidencia import capturar_pantalla
from src.parser import generar_id, limpiar_texto, parsear_estrellas, parsear_fecha, parsear_votos
from src.storage import guardar_checkpoint, guardar_crudo

log = logging.getLogger(__name__)


def configurar_logging():
    """Registro en pantalla y en scraping.log (force=True evita duplicados al re-ejecutar en Jupyter)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.FileHandler(cfg.ARCHIVO_LOG, encoding="utf-8"), logging.StreamHandler()],
        force=True,
    )


def capturar(driver, numero: int, nombre: str):
    """Captura de evidencia con nombre ordenado: scraping_04_250_resenas.png, etc."""
    capturar_pantalla(driver, cfg.DIR_CAPTURAS / f"scraping_{numero:02d}_{nombre}.png")


def abrir_modal(driver) -> WebElement:
    """Hace clic en 'Ver todas las opiniones' y espera el modal."""
    espera = WebDriverWait(driver, cfg.TIMEOUT)
    boton = espera.until(EC.element_to_be_clickable((By.XPATH, cfg.SEL["boton_ver_todas"])))
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", boton)
    boton.click()
    modal = espera.until(EC.visibility_of_element_located((By.CSS_SELECTOR, cfg.SEL["modal"])))
    espera.until(EC.presence_of_element_located((By.CSS_SELECTOR, cfg.SEL["resena"])))
    log.info("Modal de opiniones abierto")
    return modal


def ordenar(driver, modal: WebElement, orden: str):
    """Cambia el orden de las reseñas. Google Play muestra 'Más relevantes' por defecto."""
    if orden == "Más relevantes":
        return
    espera = WebDriverWait(driver, cfg.TIMEOUT)
    primera = driver.find_element(By.CSS_SELECTOR, cfg.SEL["resena"])
    xpath_opcion = cfg.SEL["opcion_orden"].format(orden=orden)
    xpath_activo = cfg.SEL["orden_activo"].format(orden=orden)

    def opcion_visible(d):
        visibles = [o for o in d.find_elements(By.XPATH, xpath_opcion) if o.is_displayed()]
        return visibles[0] if visibles else False

    for intento in range(1, 4):
        if not opcion_visible(driver):  # el menú puede seguir abierto de un intento anterior
            modal.find_element(By.XPATH, cfg.SEL["boton_orden"]).click()
        opcion = espera.until(opcion_visible)
        time.sleep(0.6)  # el menú se abre con animación; un clic antes de que termine se pierde
        opcion.click()
        try:
            # Confirmación observable: el botón del modal ya muestra el nuevo orden
            WebDriverWait(driver, 5).until(lambda _: modal.find_elements(By.XPATH, xpath_activo))
            break
        except TimeoutException:
            log.warning("El orden no cambió (intento %d/3)", intento)
    else:
        raise RuntimeError(f"No se pudo ordenar por '{orden}'")

    # Cuando Google reemplaza la lista, la primera reseña anterior desaparece del DOM ("stale")
    try:
        espera.until(EC.staleness_of(primera))
    except TimeoutException:
        log.warning("No se detectó el refresco de la lista tras ordenar; se continúa")
    espera.until(EC.presence_of_element_located((By.CSS_SELECTOR, cfg.SEL["resena"])))
    log.info("Reseñas ordenadas por '%s'", orden)


def _texto(elemento: WebElement, selector: str) -> str | None:
    """Texto del primer hijo que coincide, o None si no existe (find_elements no lanza error)."""
    hallados = elemento.find_elements(By.CSS_SELECTOR, selector)
    return limpiar_texto(hallados[0].get_attribute("textContent")) if hallados else None


def extraer_resena(elemento: WebElement) -> dict:
    """Lee los campos de una reseña; los opcionales quedan en 0 / None si no existen."""
    usuario = _texto(elemento, cfg.SEL["usuario"]) or ""
    estrellas = elemento.find_elements(By.CSS_SELECTOR, cfg.SEL["estrellas"])
    fecha = parsear_fecha(_texto(elemento, cfg.SEL["fecha"]))
    comentario = _texto(elemento, cfg.SEL["comentario"]) or ""

    respuesta = elemento.find_elements(By.CSS_SELECTOR, cfg.SEL["respuesta"])
    respuesta_texto = _texto(respuesta[0], cfg.SEL["respuesta_texto"]) if respuesta else None
    respuesta_fecha = parsear_fecha(_texto(respuesta[0], cfg.SEL["respuesta_fecha"])) if respuesta else None

    return {
        "id_resena": generar_id(usuario, fecha, comentario),
        "usuario": usuario,
        "calificacion": parsear_estrellas(estrellas[0].get_attribute("aria-label")) if estrellas else None,
        "fecha": fecha,
        "comentario": comentario,
        "votos_utiles": parsear_votos(_texto(elemento, cfg.SEL["votos"])),
        "respuesta_empresa": respuesta_texto,
        "fecha_respuesta": respuesta_fecha,
        "app": cfg.APP_NOMBRE,
        "fecha_extraccion": datetime.now().isoformat(timespec="seconds"),
    }


def scroll_y_extraer(driver, meta: int, resenas: list[dict]) -> str:
    """Bucle principal: leer nuevas -> scroll -> esperar lote -> pausa.

    Llena `resenas` en el lugar (así lo extraído sobrevive a un error) y devuelve el motivo de parada.
    """
    contenedor = driver.find_element(By.CSS_SELECTOR, cfg.SEL["contenedor_scroll"])
    contar = lambda d: len(d.find_elements(By.CSS_SELECTOR, cfg.SEL["resena"]))  # noqa: E731
    vistos = {r["id_resena"] for r in resenas}
    procesadas = sin_cambio = 0
    proximo_checkpoint = cfg.CHECKPOINT_CADA
    capturas_pendientes = [n for n in cfg.CAPTURAS_EN if n <= meta]

    with tqdm(total=meta, desc="Reseñas", unit="reseña") as barra:
        while True:
            # 1. LEER solo las reseñas nuevas (desde la posición `procesadas`)
            elementos = driver.find_elements(By.CSS_SELECTOR, cfg.SEL["resena"])
            for elemento in elementos[procesadas:]:
                if len(resenas) >= meta:
                    break
                try:
                    resena = extraer_resena(elemento)
                except (StaleElementReferenceException, WebDriverException) as e:
                    log.warning("Reseña omitida por error: %s", type(e).__name__)
                    continue
                if resena["id_resena"] in vistos:
                    continue
                vistos.add(resena["id_resena"])
                resenas.append(resena)
                barra.update(1)
            procesadas = len(elementos)

            # Checkpoints y capturas de evidencia
            while len(resenas) >= proximo_checkpoint:
                guardar_checkpoint(resenas)
                proximo_checkpoint += cfg.CHECKPOINT_CADA
            while capturas_pendientes and len(resenas) >= capturas_pendientes[0]:
                n = capturas_pendientes.pop(0)
                capturar(driver, 4 + cfg.CAPTURAS_EN.index(n), f"{n}_resenas")

            # Criterios de parada
            if len(resenas) >= meta:
                return "meta alcanzada"
            if sin_cambio >= cfg.MAX_SCROLLS_SIN_CAMBIO:
                return f"sin reseñas nuevas tras {sin_cambio} scrolls"

            # 2. SCROLL al fondo del contenedor del modal + 3. ESPERAR el nuevo lote
            antes = procesadas
            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", contenedor)
            try:
                WebDriverWait(driver, cfg.ESPERA_CARGA).until(lambda d: contar(d) > antes)
                sin_cambio = 0
            except TimeoutException:
                sin_cambio += 1
                log.warning("Scroll sin reseñas nuevas (%d/%d)", sin_cambio, cfg.MAX_SCROLLS_SIN_CAMBIO)
                # La carga perezosa se dispara cuando el final de la lista *vuelve* a verse:
                # se sube una pantalla para que el siguiente scroll al fondo la reactive.
                driver.execute_script(
                    "arguments[0].scrollTop = Math.max(0, arguments[0].scrollTop - arguments[0].clientHeight)",
                    contenedor)

            # 4. PAUSA aleatoria (cortesía con el sitio)
            time.sleep(random.uniform(cfg.PAUSA_MIN, cfg.PAUSA_MAX))


def ejecutar(meta: int = cfg.META, headless: bool = False) -> list[dict]:
    """Scraping completo: abre Chrome, extrae `meta` reseñas, guarda y cierra pase lo que pase."""
    configurar_logging()
    inicio = time.time()
    resenas: list[dict] = []
    motivo = "error o interrupción"

    driver = crear_driver(headless=headless)
    try:
        chrome, chromedriver = versiones(driver)
        log.info("Inicio | meta=%d | Chrome %s | ChromeDriver %s", meta, chrome, chromedriver)
        driver.get(cfg.URL)
        WebDriverWait(driver, cfg.TIMEOUT).until(EC.title_contains(cfg.APP_NOMBRE))
        capturar(driver, 1, "pagina_app")

        modal = abrir_modal(driver)
        capturar(driver, 2, "modal_opiniones")
        ordenar(driver, modal, cfg.ORDEN)
        capturar(driver, 3, "orden_recientes")

        motivo = scroll_y_extraer(driver, meta, resenas)
        capturar(driver, 7, "final")
    except BaseException as error:  # incluye Ctrl+C; se registra el detalle y se relanza
        motivo = f"{type(error).__name__}: {str(error).splitlines()[0] if str(error) else 'sin mensaje'}"
        log.exception("La ejecución se detuvo por un error")
        raise
    finally:
        guardar_crudo(resenas)
        driver.quit()
        log.info("Fin | %d reseñas | %.0f s | motivo: %s", len(resenas), time.time() - inicio, motivo)
    return resenas


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraping de reseñas de Rappi en Google Play")
    parser.add_argument("--meta", type=int, default=cfg.META, help="cantidad de reseñas a extraer")
    parser.add_argument("--headless", action="store_true", help="sin ventana (no sirve para evidencia)")
    args = parser.parse_args()
    ejecutar(meta=args.meta, headless=args.headless)
