# Task03 — Web scraping de reseñas de Rappi (Google Play) · Grupo 1

Extracción automatizada de ~1000 reseñas en español de la app **Rappi** desde Google Play,
usando **Selenium** y **ChromeDriver** en un entorno **Anaconda**.

- **Fuente:** https://play.google.com/store/apps/details?id=com.grability.rappi&hl=es_419&gl=PE
- **Por qué Rappi / Google Play:** más de 2,3 millones de opiniones, contenido en español,
  no requiere iniciar sesión. Se descartó Amazon (exige login para ver más reseñas) y
  Booking (bloqueos anti-bot).

## Instalación

```bash
# Requisitos: Google Chrome, Anaconda/Miniconda y LibreOffice (para exportar la presentación a PDF)
conda env create -f environment.yml
conda activate task03          # obligatorio: activa también el selenium-manager del entorno
```

ChromeDriver no se descarga a mano: **Selenium Manager** obtiene automáticamente la versión
compatible con el Chrome instalado (queda en `~/.cache/selenium/`).

## Ejecución

```bash
python prueba_rapida.py       # Fase 0: verifica Chrome + ChromeDriver
python inspeccion.py          # Fase 1: reconocimiento del sitio y selectores
python -m tests.test_parser   # pruebas de conversión de datos
jupyter lab                   # abrir G1_task03_scraping_rappi.ipynb (kernel: task03)
```

## Estructura

| Ruta | Contenido |
|---|---|
| `src/config.py` | URL, selectores, metas, pausas y rutas (único lugar a editar si Google cambia la página) |
| `src/driver.py` | Apertura de Chrome en español + versiones de Chrome/ChromeDriver |
| `src/parser.py` | Conversión de textos a datos (estrellas, fechas, votos, id) |
| `src/scraper.py` | Navegación: modal, orden, scroll y extracción |
| `src/storage.py` | Checkpoints, limpieza y validaciones |
| `src/analisis.py` | Indicadores clave y gráficos (`evidencia/graficos/`) |
| `src/presentacion.py` | Presentación de evidencia (15 diapositivas) → `entregables/G1_task03_evidencia.pdf` (copia editable en `evidencia/G1_task03_evidencia.pptx`); `python -m src.presentacion` |
| `src/exportacion.py` | CSV + XLSX (Reseñas, Diccionario, Resumen) + `LEEME.txt` → `entregables/G1_task03_data.zip`, verificado |
| `G1_task03_scraping_rappi.ipynb` | Notebook principal: scraping, limpieza, validaciones, estadísticas y conclusiones |
| `src/evidencia.py` | Capturas de pantalla completa y generación del PPT |
| `data/raw/`, `data/processed/` | Datos en crudo y limpios |
| `evidencia/capturas/` | Capturas del Chrome automatizado |
| `entregables/` | Los 3 entregables: `G1_task03_codigo.zip`, `G1_task03_data.zip`, `G1_task03_evidencia.pdf` |

## Hallazgos de la Fase 1 (08/10/2026)

| Campo | Selector | Presente (muestra de 120) |
|---|---|---|
| Reseña | `div.RHo1pe` | 120 |
| Usuario | `div.X5PpBb` | 120 |
| Calificación | `div[role='img']` → `aria-label` ("Calificación: 1 de cinco estrellas") | 120 |
| Fecha | `span.bp9Aid` ("18 de septiembre de 2026") | 120 |
| Comentario | `div.h3YV2d` (máx. 500 caracteres, nunca truncado) | 120 |
| Votos útiles | `div.AJTPZc` ("…les resultó útil a 6 personas") | 114 |
| Respuesta de Rappi | `div.ocpBU` → `div.ras4vb` / `div.I9Jtec` | 117 |

- El modal carga **20 reseñas por scroll** (~0,3 s) en el contenedor `div.fysCi`.
- Se usa el orden **"Más recientes"**: reseñas variadas (cortas y largas) y reproducibles.
- `robots.txt` no restringe `/store/apps/details`.

## Uso responsable

Uso exclusivamente académico, sin inicio de sesión, una sola sesión de navegador y pausas
aleatorias entre scrolls para no sobrecargar el sitio.
