"""Diagrama del flujo de un mensaje (Mermaid → PNG) para el notebook y la presentación.

El texto Mermaid es la fuente editable; `python -m src.diagrama` lo dibuja con Playwright (mermaid.js desde
su CDN) en evidencia/flujo_mensaje.png y guarda también evidencia/flujo_mensaje.mmd.
"""

from __future__ import annotations

from pathlib import Path

from src.config import DIR_EVIDENCIA

MERMAID_VERSION = "11.4.1"
PNG = DIR_EVIDENCIA / "flujo_mensaje.png"
FUENTE = DIR_EVIDENCIA / "flujo_mensaje.mmd"

MERMAID = """flowchart LR
    M([Mensaje]) --> P{"¿Pregunta<br/>pendiente?"}
    P -- sí --> MEM["Memoria:<br/>guarda el dato<br/>y retoma"]
    MEM --> N
    P -- no --> R{"1 · REGLAS<br/>¿patrón?"}
    R -- sí --> RR(["Respuesta fija<br/>o rechazo"])
    R -- no --> N{"2 · NLP/ML<br/>intención<br/>y confianza"}
    N -- aclarar --> A(["Alcance,<br/>«¿X o Y?»<br/>o pide un dato"])
    N -- buscar --> T{"3 · RECUPERACIÓN<br/>¿FAQ parecida<br/>y general?"}
    T -- sí --> FQ(["FAQ tal cual<br/>+ fuente"])
    T -- no --> L{"4 · LLM<br/>¿Gemini?"}
    L -- sí --> G(["Respuesta<br/>con citas"])
    L -- no --> X(["Cita textual<br/>del artículo"])

    classDef reglas fill:#6e40c9,stroke:#6e40c9,color:#fff
    classDef nlp fill:#0969da,stroke:#0969da,color:#fff
    classDef ret fill:#1a7f37,stroke:#1a7f37,color:#fff
    classDef llm fill:#bf3989,stroke:#bf3989,color:#fff
    classDef neutro fill:#f6f8fa,stroke:#57606a,color:#1f2328
    class R,RR reglas
    class N,A,MEM nlp
    class T,FQ ret
    class L,G,X llm
    class M,P neutro
"""

PAGINA = """<!doctype html><html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/mermaid@{version}/dist/mermaid.min.js"></script>
<style>body{{margin:0;padding:24px;background:#fff;font-family:system-ui,sans-serif}} .mermaid svg{{max-width:none!important}}</style></head>
<body><pre class="mermaid">{fuente}</pre>
<script>mermaid.initialize({{startOnLoad:true, theme:"base", flowchart:{{curve:"basis", padding:12, useMaxWidth:false, nodeSpacing:28, rankSpacing:38}},
themeVariables:{{fontSize:"18px", lineColor:"#57606a", edgeLabelBackground:"#ffffff"}}}});</script></body></html>"""


def generar() -> Path:
    from playwright.sync_api import sync_playwright

    DIR_EVIDENCIA.mkdir(parents=True, exist_ok=True)
    FUENTE.write_text(MERMAID, encoding="utf-8")
    html = DIR_EVIDENCIA / "flujo_mensaje.html"
    html.write_text(PAGINA.format(version=MERMAID_VERSION, fuente=MERMAID), encoding="utf-8")
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page(viewport={"width": 2400, "height": 1000}, device_scale_factor=2)
        pagina.goto(html.as_uri())
        pagina.wait_for_selector(".mermaid svg", timeout=30000)
        pagina.locator(".mermaid svg").screenshot(path=str(PNG))
        navegador.close()
    html.unlink()
    return PNG


if __name__ == "__main__":
    print(f"✅ {generar()}")
