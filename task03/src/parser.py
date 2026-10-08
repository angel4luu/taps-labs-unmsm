"""Conversión de textos de la página a datos limpios (funciones puras, sin Selenium)."""
import hashlib
import re
from datetime import date

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}


INVISIBLES = re.compile(r"[​‌‍⁠﻿]")  # espacios de ancho cero, BOM


def limpiar_texto(texto: str | None) -> str:
    """Quita caracteres invisibles y une saltos de línea y espacios repetidos en uno solo.

    Conserva tildes, ñ, emojis y mayúsculas: el texto original del usuario no se altera.
    """
    return re.sub(r"\s+", " ", INVISIBLES.sub("", texto or "")).strip()


def parsear_estrellas(aria_label: str | None) -> int | None:
    """'Calificación: 1 de cinco estrellas' -> 1"""
    m = re.search(r"(\d)\s+de\s+cinco", aria_label or "")
    return int(m.group(1)) if m else None


def parsear_fecha(texto: str | None) -> str | None:
    """'18 de septiembre de 2026' -> '2026-09-18' (ISO)"""
    m = re.search(r"(\d{1,2}) de ([a-záéíóú]+) de (\d{4})", (texto or "").lower())
    if not m or m.group(2) not in MESES:
        return None
    return date(int(m.group(3)), MESES[m.group(2)], int(m.group(1))).isoformat()


def parsear_votos(texto: str | None) -> int:
    """'Esta opinión les resultó útil a 1.234 personas' -> 1234; sin texto -> 0"""
    m = re.search(r"útil a ([\d.,]+)", texto or "")
    return int(re.sub(r"[.,]", "", m.group(1))) if m else 0


def generar_id(usuario: str, fecha: str | None, comentario: str) -> str:
    """Hash estable de la reseña, para detectar duplicados."""
    return hashlib.sha1(f"{usuario}|{fecha}|{comentario}".encode("utf-8")).hexdigest()
