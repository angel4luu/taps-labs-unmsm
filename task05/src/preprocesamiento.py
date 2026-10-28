"""Preprocesamiento de texto en español: normalizar → tokenizar → stopwords → raíces (stemming)."""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from nltk.stem.snowball import SnowballStemmer

from src.modelos import Mensaje

MAX_CARACTERES = 1000

# Palabras interrogativas: son stopwords en NLTK pero indican la intención ("cuándo" → calendario)
INTERROGATIVAS = {"cuando", "como", "donde", "que", "cuanto", "cuantos", "cuantas", "cual", "quien"}

_stemmer = SnowballStemmer("spanish")


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes (la ñ se conserva), solo letras, dígitos y espacios."""
    texto = texto.lower().replace("ñ", "\0")
    texto = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    texto = texto.replace("\0", "ñ")
    texto = re.sub(r"[^a-zñ0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def tokenizar(texto: str) -> list[str]:
    return re.findall(r"\w+", texto)


@lru_cache(maxsize=1)
def stopwords_es() -> frozenset[str]:
    import nltk
    from nltk.corpus import stopwords

    try:
        palabras = stopwords.words("spanish")
    except LookupError:
        nltk.download("stopwords", quiet=True)
        palabras = stopwords.words("spanish")
    return frozenset(normalizar(p) for p in palabras) - INTERROGATIVAS


def quitar_stopwords(tokens: list[str]) -> list[str]:
    sw = stopwords_es()
    return [t for t in tokens if t not in sw]


def stem(tokens: list[str]) -> list[str]:
    return [_stemmer.stem(t) for t in tokens]


def truncar(texto: str, max_caracteres: int = MAX_CARACTERES) -> str:
    return texto.strip()[:max_caracteres]


def raices(texto: str) -> list[str]:
    """Cadena completa; se usa como analizador de TF-IDF en intenciones y recuperación."""
    return stem(quitar_stopwords(tokenizar(normalizar(texto))))


def procesar(texto: str, turno: int = 0, max_caracteres: int = MAX_CARACTERES) -> Mensaje:
    original = truncar(texto, max_caracteres)
    normalizado = normalizar(original)
    return Mensaje(texto_original=original, texto_normalizado=normalizado, tokens=raices(original), turno=turno)


def pasos(texto: str) -> list[tuple[str, object]]:
    """Cada paso intermedio, para mostrarlo en el notebook (FR-010)."""
    normalizado = normalizar(texto)
    tokens = tokenizar(normalizado)
    sin_sw = quitar_stopwords(tokens)
    return [
        ("1. Normalización", normalizado),
        ("2. Tokenización", tokens),
        ("3. Sin stopwords", sin_sw),
        ("4. Stemming (raíces)", stem(sin_sw)),
        ("5. Texto para TF-IDF", " ".join(stem(sin_sw))),
    ]
