"""Embeddings multilingües compartidos: rama semántica del clasificador y re-ranking de recuperación."""

from __future__ import annotations

from functools import lru_cache

import numpy as np

# mpnet (768 dim) reemplaza a MiniLM (384): en validación cruzada la rama B subió de 0.715 a 0.741
# y la combinación A+B de 0.805 a 0.841 (ver research.md R4)
MODELO = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"

_cache_lote: dict[str, np.ndarray] = {}


@lru_cache(maxsize=1)
def modelo():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODELO, device="cpu")


def codificar(textos: list[str]) -> np.ndarray:
    """Vectores normalizados (el producto punto es la similitud coseno), con caché por texto."""
    faltantes = [t for t in dict.fromkeys(textos) if t not in _cache_lote]
    if faltantes:
        for t, v in zip(faltantes, modelo().encode(faltantes, normalize_embeddings=True, batch_size=64)):
            _cache_lote[t] = v
    return np.vstack([_cache_lote[t] for t in textos]) if textos else np.zeros((0, 768))


def disponible() -> bool:
    try:
        modelo()
        return True
    except Exception:
        return False
