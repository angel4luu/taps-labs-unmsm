"""Configuración central: URL, selectores verificados en la Fase 1, metas, tiempos y rutas."""
from pathlib import Path

# --- Grupo y caso de uso ---
GRUPO = "G1"
PREFIJO = f"{GRUPO}_task03"
TAREA = "Tarea 03"
CURSO = "Taller de Aplicaciones Sociales"
INTEGRANTES = [
    "Ayala Alberca Sebastian",
    "Gamarra Chavez, Diego Valentino",
    "Reyes Fabian, Jhan Brayan Zamir",
    "Jara Espinoza, Angela Lucia",
]
APP_NOMBRE = "Rappi"
OPINIONES_GOOGLE_PLAY = "2,37 M"  # total mostrado en la ficha de la app (observado el 08/10/2026)
APP_ID = "com.grability.rappi"
URL = f"https://play.google.com/store/apps/details?id={APP_ID}&hl=es_419&gl=PE"

# --- Metas y tiempos ---
META = 1050                       # reseñas en crudo (≈1000 tras la limpieza)
TIMEOUT = 20                      # segundos máximos de WebDriverWait
PAUSA_MIN, PAUSA_MAX = 0.8, 2.0   # pausa aleatoria entre scrolls (cortesía con el sitio)
ESPERA_CARGA = 10                 # segundos máximos esperando un nuevo lote tras cada scroll
MAX_SCROLLS_SIN_CAMBIO = 8        # criterio de parada si el modal deja de cargar
CHECKPOINT_CADA = 200             # guardar avance cada N reseñas
CAPTURAS_EN = (250, 500, 1000)    # capturas de evidencia al alcanzar estas cantidades
ORDEN = "Más recientes"           # "Más recientes" o "Más relevantes"
RANGO_REGISTROS = (1000, 1100)    # requisito del lab: "en el rango de 1000 registros"

# --- Selectores (verificados en la Fase 1, 08/10/2026) ---
# Las clases de Google están ofuscadas y pueden cambiar: si el scraper falla, se edita solo aquí.
SEL = {
    "boton_ver_todas": "//button[.//span[contains(., 'Ver todas las opiniones')]]",   # XPath
    "modal": "div[role='dialog']",
    "contenedor_scroll": "div[role='dialog'] div.fysCi",
    "boton_orden": ".//*[@role='button'][.//span[contains(., 'Más relevantes')]]",  # XPath relativo al modal
    "orden_activo": ".//*[@role='button'][.//span[normalize-space()='{orden}']]",   # botón ya cambiado
    "opcion_orden": "//*[@role='menuitemradio' or @role='option' or @role='menuitem'][contains(., '{orden}')]",
    "resena": "div[role='dialog'] div.RHo1pe",
    "usuario": "div.X5PpBb",
    "estrellas": "div[role='img'][aria-label]",
    "fecha": "span.bp9Aid",
    "comentario": "div.h3YV2d",
    "votos": "div.AJTPZc",                 # opcional (≈5% de reseñas no lo tienen)
    "respuesta": "div.ocpBU",              # opcional: bloque de respuesta de la empresa
    "respuesta_texto": "div.ras4vb",
    "respuesta_fecha": "div.I9Jtec",
}

# --- Rutas ---
BASE = Path(__file__).resolve().parent.parent
DIR_RAW = BASE / "data" / "raw"
DIR_PROCESADA = BASE / "data" / "processed"
DIR_INSPECCION = BASE / "data" / "inspeccion"
DIR_CAPTURAS = BASE / "evidencia" / "capturas"
DIR_GRAFICOS = BASE / "evidencia" / "graficos"
DIR_ENTREGABLES = BASE / "entregables"
ARCHIVO_LOG = BASE / "scraping.log"
