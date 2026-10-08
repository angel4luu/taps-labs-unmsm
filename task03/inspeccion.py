"""Fase 1 - Reconocimiento del sitio.

Abre la página de Rappi, abre el modal de opiniones, hace scroll unas veces midiendo
cuántas reseñas se cargan, y guarda el HTML para identificar los selectores.
"""
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.config import DIR_CAPTURAS, DIR_INSPECCION, TIMEOUT, URL
from src.driver import crear_driver
from src.evidencia import capturar_pantalla

DIR_INSPECCION.mkdir(parents=True, exist_ok=True)

# JS: devuelve el primer elemento dentro del modal que realmente tiene scroll vertical
JS_CONTENEDOR_SCROLL = """
const modal = document.querySelector("div[role='dialog']");
for (const el of modal.querySelectorAll('*')) {
  const s = getComputedStyle(el);
  if (/(auto|scroll)/.test(s.overflowY) && el.scrollHeight > el.clientHeight + 10) return el;
}
return null;
"""

# JS: cuenta reseñas por un rasgo estable (cada una tiene un div de estrellas con aria-label)
JS_CONTAR = """
return document.querySelectorAll(
  "div[role='dialog'] div[role='img'][aria-label*='estrella']").length;
"""

driver = crear_driver()
espera = WebDriverWait(driver, TIMEOUT)
try:
    driver.get(URL)

    # Paso 1: botón "Ver todas las opiniones"
    boton = espera.until(EC.element_to_be_clickable(
        (By.XPATH, "//button[.//span[contains(., 'Ver todas las opiniones')]]")))
    print("[Paso 1] Botón encontrado:", repr(boton.text))
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", boton)
    capturar_pantalla(driver, DIR_CAPTURAS / "01_pagina_app.png")
    boton.click()

    modal = espera.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "div[role='dialog']")))
    time.sleep(2)
    capturar_pantalla(driver, DIR_CAPTURAS / "02_modal_opiniones.png")

    # Paso 2: contenedor con scroll y velocidad de carga
    contenedor = driver.execute_script(JS_CONTENEDOR_SCROLL)
    print("[Paso 2] Contenedor de scroll:", contenedor.tag_name, "| class =",
          contenedor.get_attribute("class"))
    print("         Reseñas iniciales:", driver.execute_script(JS_CONTAR))
    for i in range(1, 6):
        t0 = time.time()
        antes = driver.execute_script(JS_CONTAR)
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", contenedor)
        while driver.execute_script(JS_CONTAR) == antes and time.time() - t0 < 10:
            time.sleep(0.2)
        print(f"         Scroll {i}: {driver.execute_script(JS_CONTAR)} reseñas "
              f"(+{driver.execute_script(JS_CONTAR) - antes} en {time.time() - t0:.1f}s)")
    capturar_pantalla(driver, DIR_CAPTURAS / "03_modal_scroll.png")

    # Pasos 3-5: guardar el HTML para mapear selectores y formatos
    (DIR_INSPECCION / "modal.html").write_text(modal.get_attribute("outerHTML"), encoding="utf-8")
    print("[Pasos 3-5] HTML del modal guardado en", DIR_INSPECCION / "modal.html")

    # Paso 6: cambiar el orden a "Más recientes" y verificar con las fechas
    orden = modal.find_element(By.XPATH, ".//*[@role='button'][.//span[contains(., 'Más relevantes')]]")
    orden.click()
    opcion = espera.until(EC.element_to_be_clickable(
        (By.XPATH, "//*[@role='menuitemradio' or @role='option' or @role='menuitem']"
                   "[contains(., 'Más recientes')]")))
    print("[Paso 6] Opciones de orden:", [o.text for o in driver.find_elements(
        By.XPATH, "//*[@role='menuitemradio' or @role='option' or @role='menuitem'][string-length(.) > 0]")
        if "Más" in o.text])
    opcion.click()
    time.sleep(2)
    print("         Fechas tras ordenar:",
          [f.text for f in modal.find_elements(By.CSS_SELECTOR, "div.RHo1pe span.bp9Aid")[:8]])
    capturar_pantalla(driver, DIR_CAPTURAS / "04_modal_mas_recientes.png")

    # Paso 7: robots.txt
    driver.get("https://play.google.com/robots.txt")
    (DIR_INSPECCION / "robots.txt").write_text(driver.find_element(By.TAG_NAME, "body").text,
                                               encoding="utf-8")
    print("[Paso 7] robots.txt guardado")
finally:
    driver.quit()
