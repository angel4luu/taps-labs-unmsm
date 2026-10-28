# Tarea 05 — Chatbot Híbrido · Grupo 1

Asistente académico para estudiantes de **pregrado de la UNMSM** (matrícula, repitencia, reserva y
retiro, créditos, grados y títulos, trámites, calendario, bienestar y biblioteca) que combina cuatro
componentes en un orden fijo:

```
mensaje → Reglas → NLP/ML (intención + entidades + política) → Retrieval (filtrado por intención) → LLM (RAG)
```

Cada respuesta muestra qué componente la produjo y qué política se aplicó (pedir un detalle, confirmar el
tema, memoria de sesión, rechazo, fuera de dominio, sin filtro, modo sin conexión).

- **Fuentes oficiales:** [Reglamento General de Matrícula Pregrado 2026 (RR N°002642-2026)](https://cdn.www.gob.pe/uploads/document/file/9508789/7072215-reglamento-general-de-matricula-pregrado-2026-rr-n-002642-2026.pdf)
  (60 pasajes, por artículo) y Ley Universitaria N° 30220, Art. 102 (transcrito).
- **No localizado:** el Reglamento General de Grados y Títulos de la UNMSM no está publicado en texto
  completo (solo su modificatoria RR 003078-2022, búsqueda del 27/10/2026). El tema de grados y títulos se
  cubre con FAQ referenciales que remiten a la oficina de la facultad.

## Guía rápida de instalación

Para ejecutar el notebook con todo lo necesario (el modelo de intención ya entrenado, la base de
conocimiento y el reglamento incluidos):

1. Descomprime `G1_task05_codigo.zip` y entra a la carpeta `task05/`.
2. Crea el entorno (Python 3.11), con conda **o** con pip:
   ```bash
   conda env create -f environment.yml && conda activate task05
   # o bien: python -m venv .venv && source .venv/bin/activate
   #         pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
   python -m spacy download es_core_news_sm
   ```
3. *(Opcional)* Para respuestas redactadas por Gemini, copia `.env.example` a `.env` y escribe tu
   `GEMINI_API_KEY`. Sin clave todo funciona igual; el componente LLM cita el artículo del reglamento.
4. Abre `G1_task05_chatbot_hibrido.ipynb` (desde la carpeta `task05/`) con el kernel del entorno y ejecuta
   todas las celdas (*Run All*). La primera vez se descarga el modelo de embeddings (≈ 1 GB).

El chat interactivo de la sección 7.2 funciona al ejecutar el notebook; abierto sin kernel solo muestra la
conversación de ejemplo.

## Instalación completa (desarrollo)

Además de lo anterior, para regenerar las capturas y la presentación se necesitan LibreOffice y:

```bash
python -c "import nltk; nltk.download('stopwords')"   # (se descarga sola si falta)
playwright install chromium                            # capturas de las conversaciones
```

**Clave de Gemini (opcional):** copia `.env.example` a `.env` (no se versiona) y completa
`GEMINI_API_KEY=...`. Sin clave el chatbot funciona igual: en lugar de redactar, cita el artículo
del reglamento más relevante. Opcional: `CHATBOT_LLM_LOCAL=Qwen/Qwen2.5-0.5B-Instruct` activa un modelo local
pequeño para redactar sin conexión (≈ 1 GB, respuestas de menor calidad).
La primera ejecución también descarga el modelo de embeddings (≈ 1.1 GB).

## Ejecución

```bash
python -m src.conocimiento      # descarga el reglamento (data/raw/) y genera data/conocimiento/pasajes.jsonl
python -m src.intenciones       # compara 5 clasificadores (CV), selecciona, evalúa en prueba → evidencia/evaluacion/
python -m src.recuperacion      # ajusta el umbral de recuperación (dev) y mide en prueba
python -m src.evaluacion        # recuperación con filtro de intención (SC-003)
python -m src.flujos --capturas # corre los 4 casos de uso y las escenas, los verifica y los captura
python -m src.llm --revision    # respuestas a 16 preguntas abiertas → evidencia/revision_llm.csv
python -m src.diagrama          # diagrama del flujo (Mermaid → evidencia/flujo_mensaje.png)
python -m src.presentacion      # → entregables/G1_task05_capturas.pptx y .pdf
python -m src.empaquetar        # → entregables/G1_task05_codigo.zip (proyecto completo, sin .env)
python -m pytest tests -q       # 80 pruebas + 1 fallo esperado documentado (ver Resultados)
jupyter lab                     # abrir G1_task05_chatbot_hibrido.ipynb (kernel del entorno task05)

# notebook entregable (ejecutado, con el estado del chat guardado para que se vea sin kernel):
jupyter nbconvert --to notebook --execute G1_task05_chatbot_hibrido.ipynb --output-dir entregables \
  --ExecutePreprocessor.timeout=900 --ExecutePreprocessor.store_widget_state=True
```

El chat interactivo (sección 7.2) necesita un kernel en ejecución; en el notebook ya ejecutado se ve una
conversación de ejemplo y una vista estática del widget.

`CHATBOT_LLM_MODO=offline` fuerza el modo sin conexión; `CHATBOT_LLM_MODEL=gemini-3.5-flash-lite` usa el
modelo de Gemini más liviano.

## Estructura

| Ruta | Contenido |
|---|---|
| `G1_task05_chatbot_hibrido.ipynb` | Notebook principal: explica cada componente, muestra su código, los 4 casos de uso y el chat |
| `src/config.py` | Rutas, umbrales y ajustes del LLM (variables de entorno); nunca lee ni imprime la clave |
| `src/modelos.py` | Tipos compartidos: Mensaje, Respuesta, Sesión, Detalle, componentes y políticas |
| `src/preprocesamiento.py` | Normalización, tokenización, stopwords y stemming (con vista paso a paso) |
| `src/reglas.py` | **Componente 1** — reglas y guardarraíles (`data/reglas/patrones.yaml`) |
| `src/intenciones.py` | **Componente 2** — 5 candidatos, validación cruzada, regla de selección, umbrales, reporte |
| `src/entidades.py` | Detalles: regex + listas del dominio (PhraseMatcher) + NER de spaCy |
| `src/politica.py` | Bandas de confianza, detalles requeridos, preguntas pendientes, memoria, seguimiento |
| `src/conocimiento.py` | Descarga del reglamento y división en pasajes por artículo (Art. 13 por literal) |
| `src/recuperacion.py` | **Componente 3** — TF-IDF + embeddings sobre FAQ y pasajes, filtro por tema |
| `src/embeddings.py` | Embeddings multilingües compartidos (`paraphrase-multilingual-mpnet-base-v2`) |
| `src/llm.py` | **Componente 4** — Gemini (Interactions API, JSON con citas) → (opcional) modelo local → cita textual |
| `src/orquestador.py`, `src/registro.py` | Orden fijo de etapas y su construcción |
| `src/interfaz.py` | Renderer HTML de las respuestas y chat con ipywidgets |
| `src/diagrama.py` | Diagrama del flujo de un mensaje (fuente Mermaid → PNG para el notebook y la presentación) |
| `src/flujos.py`, `src/capturas.py`, `src/presentacion.py` | Flujos de demostración, capturas (Playwright) y presentación |
| `src/evaluacion.py` | Evaluación de la recuperación con la intención real del clasificador |
| `data/` | Datos de entrada escritos por el equipo (FAQ, 300 frases etiquetadas, listas, reglas, flujos, preguntas de evaluación) |
| `evidencia/` | Reporte de evaluación, gráficos, transcripciones, capturas y revisión del LLM |
| `entregables/` | `G1_task05_chatbot_hibrido.ipynb` (ejecutado) y `G1_task05_capturas.pdf` / `.pptx` |
| `tests/` | Pruebas unitarias, de integración (casos de uso y escenas) y de métricas |

## Resultados

| Componente | Resultado | Objetivo |
|---|---|---|
| Reglas | 100 % del guion (saludo, ayuda, nombre, gracias, rechazo, despedida) | 100 % ✅ |
| NLP/ML — selección | A+B (TF-IDF + embeddings) gana en CV: F1 macro 0.841 ± 0.045 (mejor individual: SVM 0.774) | — |
| NLP/ML — prueba (n=50) | F1 macro **0.834**, accuracy **0.84** (42/50) | F1 ≥ 0.80 ✅ · accuracy ≥ 0.85 ❌ (falta 1 frase) |
| Retrieval + intención — prueba | acierto@1 **0.854**, no-respuesta correcta **0.917** (con turno de confirmación) | ≥ 0.80 ✅ · ≥ 0.90 ✅ |
| Latencia | reglas/ML/retrieval < 0.2 s; Gemini 2.5–4.6 s; LLM local ≤ 8.2 s | < 2 s · < 15 s ✅ |
| LLM con Gemini — revisión manual de 16 respuestas | 13 ok, 3 parciales, **0 afirmaciones fuera de las fuentes** | 0 ✅ |
| Preguntas no cubiertas con «no lo sé» + oficina | 2 de 4 (las otras 2 no llegan al LLM: confirmación de tema o FAQ cercana) | 4 de 4 ❌ |

**Notas de método (transparencia):**
- El conjunto de prueba de intenciones (50 frases) se fijó antes de entrenar y nunca se usó para elegir.
  Se evaluó una vez con 250 frases; luego se añadieron 50 frases **solo al entrenamiento** y se cambió el
  modelo de embeddings de MiniLM a mpnet, decidiéndolo con validación cruzada (no con la prueba). El
  objetivo de accuracy 0.85 no se alcanzó y la prueba correspondiente está marcada como fallo esperado.
- La recuperación tiene dos conjuntos: *dev* (ajuste del umbral) y *prueba* (preguntas nuevas). Las FAQ
  tienen formulaciones alternativas escritas para todas por igual.
- **LLM:** la revisión (`evidencia/revision_llm.csv`) se hizo con Gemini. En modo sin conexión, el modelo
  local de 0.5B es claramente más débil: confundió una vez «segunda» y «tercera matrícula» e inventó un
  costo («$120»), que el control de fundamentación bloquea (cae a la respuesta extractiva). Por eso es
  solo un respaldo; el flujo 6 de la presentación lo muestra a propósito.

## Entregables

- `entregables/G1_task05_chatbot_hibrido.ipynb` — notebook ejecutado (con salidas y respuestas de Gemini).
- `entregables/G1_task05_capturas.pdf` y `entregables/G1_task05_capturas.pptx` (editable) — presentación:
  introducción → los 4 componentes (con sus casos límite) → 4 casos de uso completos → conclusiones.
- `entregables/G1_task05_codigo.zip` — el proyecto completo para ejecutarlo en otra computadora (código,
  datos, reglamento, modelo entrenado, pruebas, evidencia y el notebook ejecutado); ver «Guía rápida de
  instalación». No incluye ninguna clave.

El notebook necesita la carpeta del proyecto (`src/`, `data/`): solo, sin el zip, puede leerse pero no
ejecutarse.
