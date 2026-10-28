"""Componente 3 — Recuperación de información: TF-IDF + similitud coseno sobre FAQ y pasajes oficiales."""

from __future__ import annotations

import csv
import re
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.pipeline import FeatureUnion

from src import embeddings, preprocesamiento
from src.config import Config
from src.conocimiento import cargar_jsonl
from src.modelos import Componente, EntradaConocimiento, Fuente, Respuesta

PESO_PREGUNTA = 0.6  # en las FAQ pesa más el parecido con la pregunta que con la respuesta
PESO_SEMANTICO = 0.5  # mezcla léxico (TF-IDF) + semántico (embeddings) para reconocer sinónimos

# Palabras de pregunta y verbos genéricos: en recuperación no distinguen un tema de otro
# ("¿cómo hago…?" aparece tanto en "cómo hago la reserva" como en "cómo hago un ceviche")
GENERICAS = set(preprocesamiento.stem(
    "como cuando donde que cual cuales cuanto cuantos quien hacer hago hace puedo puede podria quiero quisiera "
    "tengo tiene necesito debo deberia saber dime hay ser estar".split()))


def raices_recuperacion(texto: str) -> list[str]:
    return [r for r in preprocesamiento.raices(texto) if r not in GENERICAS]
PATRON_FECHAS = re.compile(r"\b\d{1,2} de [a-záéíóú]+|S/\s?\d|\bplazos?\b|\bfechas?\b|\bd[ií]as\b|\bcronograma\b",
                           re.IGNORECASE)


def vectorizador() -> FeatureUnion:
    """Raíces (1–2 gramas) + n-gramas de caracteres (tolerancia a errores: "matricla", "reserba")."""
    return FeatureUnion([
        ("raices", TfidfVectorizer(analyzer=raices_recuperacion, sublinear_tf=True)),
        ("bigramas", TfidfVectorizer(tokenizer=raices_recuperacion, preprocessor=None, lowercase=False,
                                     token_pattern=None, ngram_range=(2, 2), sublinear_tf=True)),
        ("caracteres", TfidfVectorizer(preprocessor=preprocesamiento.normalizar, analyzer="char_wb",
                                       ngram_range=(3, 5), sublinear_tf=True)),
    ])


def recordatorio(fuentes: list[EntradaConocimiento], texto: str) -> str | None:
    """FR-029: aviso de información referencial cuando hay fechas/plazos o fuentes del equipo."""
    if not fuentes:
        return None
    if any(f.referencial for f in fuentes) or PATRON_FECHAS.search(texto):
        principal = fuentes[0]
        return (f"Información referencial (fuente: {principal.fecha_fuente}). "
                f"Confirma en {principal.oficina or 'la oficina correspondiente'}.")
    return None


class Indice:
    def __init__(self, entradas: list[EntradaConocimiento], config: Config | None = None, semantico: bool = True):
        self.config = config or Config()
        self.entradas = entradas
        self.vec = vectorizador()
        completos = [f"{e.pregunta or ''} {e.texto}" for e in entradas]
        # Cada FAQ aporta su pregunta y sus formulaciones alternativas; gana la más parecida
        self.filas_pregunta = [(i, q) for i, e in enumerate(entradas) for q in ([e.pregunta or e.texto] + e.alternativas)]
        preguntas = [q for _, q in self.filas_pregunta]
        self.fila_entrada = np.array([i for i, _ in self.filas_pregunta])
        self.vec.fit(completos + preguntas)
        self.m_completo = self.vec.transform(completos)
        self.m_pregunta = self.vec.transform(preguntas)
        self.es_faq = np.array([e.tipo == "faq" for e in entradas])
        self.semantico = semantico and embeddings.disponible()
        if self.semantico:
            self.e_completo = embeddings.codificar([f"{e.pregunta or ''} {e.texto}" for e in entradas])
            self.e_pregunta = embeddings.codificar(preguntas)
        self.temas = np.array([e.tema for e in entradas])

    @classmethod
    def desde_archivos(cls, config: Config | None = None) -> "Indice":
        config = config or Config()
        entradas = cargar_jsonl(config.ruta("conocimiento", "faq.jsonl")) + cargar_jsonl(
            config.ruta("conocimiento", "pasajes.jsonl"))
        if not entradas:
            raise FileNotFoundError("Faltan data/conocimiento/faq.jsonl y pasajes.jsonl (python -m src.conocimiento)")
        return cls(entradas, config)

    def _scores(self, consulta: str) -> np.ndarray:
        q = self.vec.transform([consulta])
        completo = cosine_similarity(q, self.m_completo)[0]
        por_fila = cosine_similarity(q, self.m_pregunta)[0]
        if self.semantico:
            qe = embeddings.codificar([consulta])[0]
            completo = (1 - PESO_SEMANTICO) * completo + PESO_SEMANTICO * np.clip(self.e_completo @ qe, 0, 1)
            por_fila = (1 - PESO_SEMANTICO) * por_fila + PESO_SEMANTICO * np.clip(self.e_pregunta @ qe, 0, 1)
        pregunta = np.zeros(len(self.entradas))
        np.maximum.at(pregunta, self.fila_entrada, por_fila)
        return np.where(self.es_faq, PESO_PREGUNTA * pregunta + (1 - PESO_PREGUNTA) * completo, completo)

    def buscar(self, consulta: str, tema: str | None = None, k: int = 3,
               solo: str | None = None) -> list[tuple[EntradaConocimiento, float]]:
        """Top-k por similitud coseno; `tema` restringe al tema de la intención (FR-019)."""
        scores = self._scores(consulta)
        mascara = np.ones(len(self.entradas), dtype=bool)
        if tema:
            mascara &= self.temas == tema
        if solo == "faq":
            mascara &= self.es_faq
        elif solo == "pasaje":
            mascara &= ~self.es_faq
        scores = np.where(mascara, scores, -1.0)
        orden = np.argsort(-scores)[:k]
        return [(self.entradas[i], float(scores[i])) for i in orden if scores[i] > 0]

    def mejor_faq(self, consulta: str, tema: str | None = None) -> tuple[EntradaConocimiento, float] | None:
        resultado = self.buscar(consulta, tema, k=1, solo="faq")
        return resultado[0] if resultado else None

    def respuesta_directa(self, consulta: str, tema: str | None = None) -> Respuesta | None:
        """FAQ más parecida si supera el umbral; su texto se devuelve tal cual, sin generar (FR-020)."""
        mejor = self.mejor_faq(consulta, tema)
        if mejor is None or mejor[1] < self.config.UMBRAL_FAQ:
            return None
        faq, score = mejor
        fuente = Fuente(id=faq.id, documento=faq.documento, ubicacion=faq.ubicacion, score=score)
        texto = faq.texto
        if faq.oficina and faq.oficina not in texto:
            texto += f"\n\nOficina de contacto: {faq.oficina}."
        return Respuesta(texto=texto, componente=Componente.RETRIEVAL, fuentes=[fuente],
                         recordatorio_referencial=recordatorio([faq], faq.texto))

    def contexto(self, consulta: str, tema: str | None = None, k: int = 5) -> list[EntradaConocimiento]:
        """Pasajes oficiales (y FAQ como respaldo) que superan el umbral de contexto, para el LLM."""
        resultados = self.buscar(consulta, tema, k=k, solo="pasaje")
        if not resultados and tema:
            resultados = self.buscar(consulta, tema, k=k)
        return [e for e, s in resultados if s >= self.config.UMBRAL_CONTEXTO]

    # --- evaluación (SC-003) -------------------------------------------------------------------
    @staticmethod
    def leer_preguntas(ruta: Path) -> list[dict]:
        with ruta.open(encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def evaluar(self, ruta: Path, umbral: float | None = None) -> dict:
        umbral = self.config.UMBRAL_FAQ if umbral is None else umbral
        filas = self.leer_preguntas(ruta)
        aciertos = aciertos3 = n_con = correctas_sin = n_sin = 0
        for fila in filas:
            top = self.buscar(fila["pregunta"], k=3, solo="faq")
            esperado = fila["id_esperado"].strip()
            if esperado:
                n_con += 1
                aciertos += bool(top and top[0][0].id == esperado and top[0][1] >= umbral)
                aciertos3 += any(e.id == esperado for e, s in top if s >= umbral)
            else:
                n_sin += 1
                correctas_sin += not (top and top[0][1] >= umbral)
        return {"umbral_faq": umbral, "hit_at_1": aciertos / max(n_con, 1), "hit_at_3": aciertos3 / max(n_con, 1),
                "no_respuesta_correcta": correctas_sin / max(n_sin, 1), "n_con_respuesta": n_con,
                "n_sin_respuesta": n_sin}

    def ajustar_umbrales(self, ruta: Path) -> dict:
        """Busca el umbral FAQ que maximiza el acierto manteniendo ≥ 0.90 de no-respuesta correcta."""
        mejor = None
        for umbral in np.arange(0.05, 0.61, 0.01):
            m = self.evaluar(ruta, float(round(umbral, 2)))
            if m["no_respuesta_correcta"] >= 0.90 and (mejor is None or m["hit_at_1"] > mejor["hit_at_1"]):
                mejor = m
        mejor = mejor or self.evaluar(ruta)
        self.config.UMBRAL_FAQ = mejor["umbral_faq"]
        # El contexto para el LLM es más permisivo: la mitad del umbral de respuesta directa
        mejor["umbral_contexto"] = round(self.config.UMBRAL_FAQ / 2, 2)
        self.config.UMBRAL_CONTEXTO = mejor["umbral_contexto"]
        return mejor


def guardar_ajuste(config: Config | None = None) -> dict:
    """Ajusta el umbral en el conjunto dev y mide en el de prueba; guarda ambos en reporte.json."""
    import json

    from src.config import REPORTE_EVALUACION

    config = config or Config()
    indice = Indice.desde_archivos(config)
    dev = indice.ajustar_umbrales(config.ruta("evaluacion", "preguntas_retrieval_dev.csv"))
    prueba = indice.evaluar(config.ruta("evaluacion", "preguntas_retrieval.csv"))
    reporte = json.loads(REPORTE_EVALUACION.read_text(encoding="utf-8")) if REPORTE_EVALUACION.exists() else {}
    reporte.setdefault("umbrales", {}).update({"faq": dev["umbral_faq"], "contexto": dev["umbral_contexto"]})
    reporte.setdefault("retrieval", {}).update({"dev": dev, "prueba_componente": prueba})
    REPORTE_EVALUACION.parent.mkdir(parents=True, exist_ok=True)
    REPORTE_EVALUACION.write_text(json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"dev": dev, "prueba": prueba}


def etapa(indice: Indice):
    def _etapa(mensaje, sesion, contexto):
        # Preguntas personalizadas (con detalles, de seguimiento o de varias partes) van al LLM con contexto
        if not contexto.preferir_llm:
            respuesta = indice.respuesta_directa(mensaje.texto_original, contexto.tema)
            if respuesta is not None:
                return respuesta
        consulta = mensaje.texto_original
        if contexto.seguimiento and sesion.historial:  # "¿y si…?" se busca junto con la pregunta anterior
            consulta = f"{sesion.historial[-1][0].texto_original} {consulta}"
        contexto.pasajes = indice.contexto(consulta, contexto.tema)
        return None

    return _etapa


if __name__ == "__main__":
    resultado = guardar_ajuste()
    for nombre, m in resultado.items():
        print(f"{nombre:<7} umbral={m['umbral_faq']:.2f}  acierto@1={m['hit_at_1']:.3f}  acierto@3={m['hit_at_3']:.3f}  "
              f"no-respuesta={m['no_respuesta_correcta']:.3f}")
