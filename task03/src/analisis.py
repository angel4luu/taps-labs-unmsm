"""Estadísticas descriptivas y gráficos del dataset limpio (para el notebook y el PPT)."""
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from src.config import APP_NOMBRE, DIR_GRAFICOS

# Paleta: una sola serie por gráfico -> un solo color; texto en tinta neutra, rejilla recesiva
SERIE = "#2a78d6"
SUPERFICIE = "#fcfcfb"
TEXTO = "#0b0b0b"
TEXTO_SECUNDARIO = "#52514e"
REJILLA = "#e4e3df"


def resumen(df: pd.DataFrame) -> dict:
    """Indicadores clave para el notebook y la diapositiva de resultados."""
    con_respuesta = df["tiene_respuesta"]
    return {
        "Reseñas": len(df),
        "Rango de fechas": f"{df['fecha'].min():%d/%m/%Y} – {df['fecha'].max():%d/%m/%Y}",
        "Calificación promedio": round(df["calificacion"].mean(), 2),
        "% de 1 estrella": round((df["calificacion"] == 1).mean() * 100, 1),
        "% respondidas por Rappi": round(con_respuesta.mean() * 100, 1),
        "Días promedio de respuesta": round(df.loc[con_respuesta, "dias_respuesta"].mean(), 1),
        "Longitud media del comentario": int(df["longitud_comentario"].mean()),
    }


def _estilo(ax, titulo: str):
    ax.set_facecolor(SUPERFICIE)
    ax.figure.set_facecolor(SUPERFICIE)
    ax.set_title(titulo, loc="left", fontsize=13, color=TEXTO, pad=14)
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color(REJILLA)
    ax.tick_params(colors=TEXTO_SECUNDARIO, length=0)
    ax.yaxis.grid(True, color=REJILLA, linewidth=1)
    ax.set_axisbelow(True)


def grafico_calificaciones(df: pd.DataFrame, ruta: Path | None = None):
    """Barras: cantidad de reseñas por calificación (1–5 estrellas), con etiqueta directa."""
    conteo = df["calificacion"].value_counts().reindex(range(1, 6), fill_value=0)
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    barras = ax.bar([f"{i}★" for i in conteo.index], conteo.values, width=0.55, color=SERIE)
    for barra, n in zip(barras, conteo.values):
        ax.annotate(f"{n}  ({n / len(df):.0%})", (barra.get_x() + barra.get_width() / 2, n),
                    xytext=(0, 4), textcoords="offset points", ha="center", color=TEXTO, fontsize=10)
    _estilo(ax, f"Distribución de calificaciones — {APP_NOMBRE} ({len(df)} reseñas)")
    ax.set_ylabel("Reseñas", color=TEXTO_SECUNDARIO)
    ax.set_ylim(0, conteo.max() * 1.12)
    fig.tight_layout()
    return _guardar(fig, ruta or DIR_GRAFICOS / "calificaciones.png")


def grafico_por_dia(df: pd.DataFrame, ruta: Path | None = None):
    """Línea: reseñas publicadas por día."""
    por_dia = df.groupby(df["fecha"].dt.date).size()
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    ax.plot(por_dia.index, por_dia.values, color=SERIE, linewidth=2, solid_capstyle="round",
            marker="o", markersize=4, markeredgecolor=SUPERFICIE, markeredgewidth=1)
    _estilo(ax, f"Reseñas por día — {APP_NOMBRE}")
    ax.set_ylabel("Reseñas", color=TEXTO_SECUNDARIO)
    ax.set_ylim(0, por_dia.max() * 1.15)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=3))
    fig.text(0.01, 0.01, "El primer y el último día están incompletos (corte de la muestra).",
             color=TEXTO_SECUNDARIO, fontsize=8)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    return _guardar(fig, ruta or DIR_GRAFICOS / "resenas_por_dia.png")


def _guardar(fig, ruta: Path):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(ruta, facecolor=SUPERFICIE)
    return fig
