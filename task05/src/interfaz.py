"""Interfaz de chat dentro del notebook. `render_html` también genera las transcripciones de las capturas,
así las diapositivas muestran exactamente lo mismo que el widget (contracts/reply-display.md)."""

from __future__ import annotations

import html
import re

from src.modelos import Componente, Mensaje, Politica, Respuesta

COLORES = {  # fondo sólido + texto blanco: legible en tema claro y oscuro
    Componente.REGLAS: "#6e40c9",
    Componente.NLP_ML: "#0969da",
    Componente.RETRIEVAL: "#1a7f37",
    Componente.LLM: "#bf3989",
    Componente.LLM_LOCAL: "#9a6700",
    Componente.FALLBACK_EXTRACTIVO: "#57606a",
}
COLOR_POLITICA = {
    Politica.PEDIR_DETALLE: "#0550ae", Politica.CONFIRMAR_TOP2: "#0550ae", Politica.RECHAZO: "#cf222e",
    Politica.FUERA_DOMINIO: "#cf222e", Politica.MEMORIA_SESION: "#116329", Politica.FALLBACK_OFFLINE: "#7d4e00",
    Politica.SIN_FILTRO: "#57606a",
}

ESTILO = """
<style>
.chat-unmsm { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; max-width: 980px; color: #1f2328;
  background: #f6f8fa; padding: 16px; border-radius: 12px; border: 1px solid #d0d7de; }
.chat-unmsm .titulo { font-weight: 700; font-size: 15px; margin: 0 0 12px; color: #1f2328; }
.chat-unmsm .fila { display: flex; margin: 10px 0; }
.chat-unmsm .fila.usuario { justify-content: flex-end; }
.chat-unmsm .burbuja { max-width: 78%; padding: 10px 14px; border-radius: 12px; line-height: 1.45; font-size: 14px;
  white-space: pre-wrap; }
.chat-unmsm .usuario .burbuja { background: #ddf4ff; border: 1px solid #b6e3ff; color: #0a3069; }
.chat-unmsm .bot .burbuja { background: #ffffff; border: 1px solid #d0d7de; color: #1f2328; }
.chat-unmsm .etiquetas { margin-bottom: 6px; }
.chat-unmsm .badge, .chat-unmsm .chip { display: inline-block; color: #fff; font-size: 11.5px; font-weight: 600;
  padding: 2px 8px; border-radius: 10px; margin-right: 4px; }
.chat-unmsm .chip { font-weight: 500; opacity: .92; }
.chat-unmsm .fuentes { margin-top: 8px; font-size: 12.5px; color: #1a7f37; }
.chat-unmsm .recordatorio { margin-top: 6px; font-size: 12.5px; color: #9a6700; }
.chat-unmsm .detalle { margin-top: 8px; padding-top: 6px; border-top: 1px dashed #d0d7de; font-size: 11.5px;
  color: #57606a; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; white-space: normal; }
.chat-unmsm .turno { font-size: 11px; color: #57606a; margin: 0 6px; align-self: center; }
</style>
"""


def _texto(t: str) -> str:
    seguro = html.escape(t)
    return re.sub(r"\*\*(.+?)\*\*|\*(.+?)\*", lambda m: f"<b>{m.group(1) or m.group(2)}</b>", seguro)


def linea_detalle(r: Respuesta) -> str:
    partes = []
    if r.regla:
        partes.append(f"regla={r.regla}")
    elif r.intencion:
        partes.append(f"intención={r.intencion.intencion} · {r.intencion.confianza:.2f} ({r.intencion.modelo})")
    if r.detalles:
        partes.append(", ".join(d.etiqueta() for d in r.detalles if d.tipo not in {"organizacion", "lugar"}))
    partes.append(f"{r.latencia_ms} ms")
    return " · ".join(p for p in partes if p)


def burbuja_bot(r: Respuesta) -> str:
    etiquetas = f'<span class="badge" style="background:{COLORES[r.componente]}">{r.componente.value}</span>'
    etiquetas += "".join(f'<span class="chip" style="background:{COLOR_POLITICA.get(p, "#57606a")}">{p.value}</span>'
                         for p in r.politica)
    cuerpo = f'<div class="etiquetas">{etiquetas}</div>{_texto(r.texto)}'
    if r.fuentes:
        cuerpo += '<div class="fuentes">Fuentes: ' + "; ".join(html.escape(f.texto()) for f in r.fuentes) + "</div>"
    if r.recordatorio_referencial:
        cuerpo += f'<div class="recordatorio">ⓘ {html.escape(r.recordatorio_referencial)}</div>'
    cuerpo += f'<div class="detalle">{html.escape(linea_detalle(r))}</div>'
    return f'<div class="fila bot"><div class="burbuja">{cuerpo}</div></div>'


def render_html(turnos: list[tuple[Mensaje, Respuesta]], titulo: str | None = None, numerar: bool = False) -> str:
    filas = []
    for k, (mensaje, respuesta) in enumerate(turnos, start=1):
        numero = f'<span class="turno">T{k}</span>' if numerar else ""
        filas.append(f'<div class="fila usuario">{numero}<div class="burbuja">{_texto(mensaje.texto_original)}'
                     f'</div></div>')
        filas.append(burbuja_bot(respuesta))
    cabecera = f'<div class="titulo">{html.escape(titulo)}</div>' if titulo else ""
    return f'{ESTILO}<div class="chat-unmsm">{cabecera}{"".join(filas)}</div>'


def chat(orq):
    """Widget de chat: caja de conversación + campo de texto + botones Enviar y Nueva sesión."""
    import ipywidgets as w

    estado = {"sesion": orq.nueva_sesion()}
    salida = w.HTML(value=render_html([], "Asistente académico UNMSM — escribe «hola» o «ayuda» para empezar"))
    # continuous_update=False: el valor se actualiza al presionar Enter (on_submit está obsoleto)
    entrada = w.Text(placeholder="Escribe tu consulta y presiona Enter…", continuous_update=False,
                     layout=w.Layout(width="70%"))
    enviar = w.Button(description="Enviar", button_style="primary")
    nueva = w.Button(description="Nueva sesión")

    def refrescar():
        salida.value = render_html(estado["sesion"].historial, "Asistente académico UNMSM")

    def al_enviar(_=None):
        texto = entrada.value.strip()
        if not texto:
            return
        entrada.value = ""
        orq.responder(texto, estado["sesion"])
        refrescar()

    def al_reiniciar(_=None):
        estado["sesion"] = orq.nueva_sesion()
        refrescar()

    enviar.on_click(al_enviar)
    nueva.on_click(al_reiniciar)
    entrada.observe(lambda cambio: al_enviar() if cambio["new"].strip() else None, names="value")
    return w.VBox([salida, w.HBox([entrada, enviar, nueva])])
