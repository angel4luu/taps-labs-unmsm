"""Guardado de datos: checkpoints, limpieza y validación.

La exportación de entregables y el .zip están en src/exportacion.py.
"""
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from src.config import DIR_PROCESADA, DIR_RAW, RANGO_REGISTROS
from src.parser import limpiar_texto

log = logging.getLogger(__name__)

COLUMNAS_FINALES = [
    "id_resena", "usuario", "calificacion", "fecha", "comentario", "longitud_comentario",
    "votos_utiles", "tiene_respuesta", "respuesta_empresa", "fecha_respuesta", "dias_respuesta",
    "editada_tras_respuesta", "app", "fecha_extraccion",
]
OBLIGATORIAS = ["id_resena", "usuario", "calificacion", "fecha", "comentario", "app", "fecha_extraccion"]


def _guardar_csv(resenas: list[dict], ruta: Path) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig: Excel muestra bien tildes y ñ
    pd.DataFrame(resenas).to_csv(ruta, index=False, encoding="utf-8-sig")
    return ruta


def guardar_checkpoint(resenas: list[dict]) -> Path:
    """Guarda el avance en data/raw/ para no perderlo si Chrome se cae."""
    ruta = _guardar_csv(resenas, DIR_RAW / "checkpoint.csv")
    log.info("Checkpoint: %d reseñas guardadas", len(resenas))
    return ruta


def guardar_crudo(resenas: list[dict]) -> Path:
    """Guarda el resultado final del scraping, tal como se extrajo."""
    ruta = _guardar_csv(resenas, DIR_RAW / "resenas_crudas.csv")
    log.info("Datos en crudo: %d reseñas en %s", len(resenas), ruta)
    return ruta


def cargar_crudo() -> pd.DataFrame:
    """Lee data/raw/resenas_crudas.csv (el archivo crudo nunca se modifica)."""
    return pd.read_csv(DIR_RAW / "resenas_crudas.csv", encoding="utf-8-sig")


def limpiar(crudo: pd.DataFrame | list[dict]) -> tuple[pd.DataFrame, dict]:
    """Devuelve (DataFrame limpio, resumen con lo que hizo cada paso)."""
    df = pd.DataFrame(crudo).copy()
    resumen = {"registros_crudos": len(df)}

    # Paso 2: tipos de datos
    df["calificacion"] = pd.to_numeric(df["calificacion"], errors="coerce").astype("Int64")
    df["votos_utiles"] = pd.to_numeric(df["votos_utiles"], errors="coerce").fillna(0).astype(int)
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["fecha_respuesta"] = pd.to_datetime(df["fecha_respuesta"], errors="coerce")
    df["fecha_extraccion"] = pd.to_datetime(df["fecha_extraccion"], errors="coerce")

    # Paso 3: duplicados (red de seguridad; el scraper ya filtra en vivo)
    antes = len(df)
    df = df.drop_duplicates(subset="id_resena", keep="first")
    resumen["duplicados_eliminados"] = antes - len(df)

    # Paso 4: normalizar texto (sin alterar tildes, emojis ni mayúsculas)
    for col in ["usuario", "comentario", "respuesta_empresa"]:
        df[col] = df[col].map(lambda t: limpiar_texto(t) if isinstance(t, str) else t)

    # Paso 5: solo se eliminan comentarios totalmente vacíos; los cortos ("ok", "👍") se conservan
    antes = len(df)
    df = df[df["comentario"].fillna("").str.len() > 0]
    resumen["vacios_eliminados"] = antes - len(df)

    # Paso 6: respuesta ausente = nulo real (no "N/A")
    df["respuesta_empresa"] = df["respuesta_empresa"].replace("", pd.NA)

    # Paso 7: columnas derivadas
    df["longitud_comentario"] = df["comentario"].str.len()
    df["tiene_respuesta"] = df["respuesta_empresa"].notna()
    dias = (df["fecha_respuesta"] - df["fecha"]).dt.days.astype("Int64")
    # Google Play muestra la fecha de la última edición de la reseña, pero la respuesta conserva
    # su fecha original: si la respuesta es "anterior", el usuario editó su reseña después.
    df["editada_tras_respuesta"] = (dias < 0).fillna(False).astype(bool)
    df["dias_respuesta"] = dias.mask(df["editada_tras_respuesta"])  # no medible en esos casos
    resumen["editadas_tras_respuesta"] = int(df["editada_tras_respuesta"].sum())

    df = df[COLUMNAS_FINALES].sort_values("fecha", ascending=False, kind="stable").reset_index(drop=True)
    resumen["registros_finales"] = len(df)
    log.info("Limpieza: %s", resumen)
    return df, resumen


def validar(df: pd.DataFrame) -> list[str]:
    """Paso 8: comprobaciones de calidad. Lanza AssertionError si alguna falla."""
    hoy = pd.Timestamp(date.today())
    minimo, maximo = RANGO_REGISTROS
    checks = {
        f"cantidad en rango {minimo}–{maximo}": minimo <= len(df) <= maximo,
        "id_resena único": df["id_resena"].is_unique,
        "sin nulos en columnas obligatorias": not df[OBLIGATORIAS].isna().any().any(),
        "calificación entre 1 y 5": df["calificacion"].between(1, 5).all(),
        "sin fechas futuras": (df["fecha"] <= hoy).all(),
        "días de respuesta no negativos": (df["dias_respuesta"].dropna() >= 0).all(),
        "votos no negativos": (df["votos_utiles"] >= 0).all(),
    }
    fallidas = [nombre for nombre, ok in checks.items() if not ok]
    assert not fallidas, f"Validaciones fallidas: {fallidas}"
    log.info("Validaciones superadas: %d/%d", len(checks), len(checks))
    return list(checks)


def guardar_procesado(df: pd.DataFrame) -> Path:
    """Guarda el dataset limpio en data/processed/."""
    ruta = DIR_PROCESADA / "resenas_limpias.csv"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta, index=False, encoding="utf-8-sig")
    log.info("Datos limpios: %d reseñas en %s", len(df), ruta)
    return ruta
