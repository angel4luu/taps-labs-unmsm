"""Capturas de evidencia: pantalla completa (muestra la barra de "software automatizado").

En Linux con Wayland las librerías clásicas (mss, pyautogui) devuelven imágenes negras,
así que se usa el portal oficial del escritorio (org.freedesktop.portal.Screenshot).
Si falla (otro SO, sin portal), se cae a driver.save_screenshot(), que solo captura la página.
"""
import logging
import shutil
import time
import uuid
from pathlib import Path
from urllib.parse import unquote, urlparse

log = logging.getLogger(__name__)


def _captura_portal(timeout: int = 15) -> Path | None:
    """Pide al portal una captura de pantalla completa; devuelve la ruta temporal o None."""
    try:
        import gi
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib
    except (ImportError, ValueError):
        return None

    bus = Gio.bus_get_sync(Gio.BusType.SESSION)
    loop, resultado = GLib.MainLoop(), {}
    token = f"task03_{uuid.uuid4().hex[:8]}"
    remitente = bus.get_unique_name()[1:].replace(".", "_")
    ruta_request = f"/org/freedesktop/portal/desktop/request/{remitente}/{token}"

    def al_responder(_con, _rem, _ruta, _iface, _senal, params):
        codigo, datos = params.unpack()
        resultado["uri"] = datos.get("uri") if codigo == 0 else None
        loop.quit()

    sub = bus.signal_subscribe(None, "org.freedesktop.portal.Request", "Response",
                               ruta_request, None, 0, al_responder)
    try:
        bus.call_sync(
            "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Screenshot", "Screenshot",
            GLib.Variant("(sa{sv})", ("", {
                "handle_token": GLib.Variant("s", token),
                "interactive": GLib.Variant("b", False),
            })),
            None, 0, -1, None,
        )
        GLib.timeout_add_seconds(timeout, loop.quit)
        loop.run()
    except GLib.Error as e:
        log.warning("Portal de capturas no disponible: %s", e.message)
        return None
    finally:
        bus.signal_unsubscribe(sub)

    uri = resultado.get("uri")
    return Path(unquote(urlparse(uri).path)) if uri else None


def capturar_pantalla(driver, destino: Path) -> Path:
    """Guarda una captura de pantalla completa en `destino` (o solo la página, como respaldo)."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    time.sleep(0.5)  # deja que la página termine de pintarse antes de capturar
    temporal = _captura_portal()
    if temporal and temporal.exists():
        shutil.move(temporal, destino)  # el portal guarda en ~/Imágenes; lo movemos a evidencia/
        log.info("Captura de pantalla completa: %s", destino.name)
    else:
        driver.save_screenshot(str(destino))
        log.info("Captura solo de la página (respaldo): %s", destino.name)
    return destino
