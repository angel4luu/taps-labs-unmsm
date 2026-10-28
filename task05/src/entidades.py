"""Extracción de detalles (entidades): regex + listas del dominio (PhraseMatcher) + NER de spaCy."""

from __future__ import annotations

import csv
import re
from functools import lru_cache

from src.config import Config
from src.modelos import Detalle
from src.preprocesamiento import normalizar

PRIORIDAD = {"lista": 3, "regex": 2, "spacy": 1}  # en conflicto gana lista > regex > spacy
NUMEROS = {"una": 1, "un": 1, "dos": 2, "tres": 3, "cuatro": 4, "1": 1, "2": 2, "3": 3, "4": 4}
ORDINALES = {"primera": 1, "segunda": 2, "tercera": 3, "cuarta": 4}

RE_PERIODO = re.compile(r"\b(20\d\d)\s*-\s*(II|I|0)\b", re.IGNORECASE)
RE_PERIODO_RELATIVO = re.compile(r"\b(proximo|siguiente|este|presente) (ciclo|semestre)\b")
RE_VECES = re.compile(r"\b(una|un|dos|tres|cuatro|[1-4])\s*(vez|veces)\b")
RE_VECES_ORDINAL = re.compile(r"\b(?:por )?(primera|segunda|tercera|cuarta) vez\b")
RE_CODIGO = re.compile(r"\b\d{8}\b")
RE_CURSO_TRAS_VERBO = re.compile(
    r"(?:jalaron|jale|jalé|desaprobé|desaprobe|reprobé|reprobe|desaprobaron)\s+(?:en\s+)?(?:el curso de\s+)?"
    r"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+(?:I{1,3}|[12]))?)")


class Extractor:
    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.facultades = self._leer("facultades.csv")
        self.nombre_facultad = {f["id"]: f["nombre_oficial"] for f in self.facultades}
        self.nlp, self.matcher, self.valores = _spacy(self.config.dir_data)

    def _leer(self, archivo: str) -> list[dict]:
        with self.config.ruta("entidades", archivo).open(encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def extraer(self, texto: str) -> list[Detalle]:
        detalles = self._lista(texto) + self._regex(texto) + self._spacy(texto)
        return _resolver_conflictos(detalles)

    # --- listas del dominio --------------------------------------------------------------------
    def _lista(self, texto: str) -> list[Detalle]:
        doc = self.nlp.make_doc(normalizar(texto))
        encontrados = []
        for id_regla, inicio, fin in self.matcher(doc):
            tipo, valor = self.valores[self.nlp.vocab.strings[id_regla]]
            encontrados.append((inicio, fin, tipo, valor, doc[inicio:fin].text))
        # Se queda con la coincidencia más larga cuando se solapan ("ingenieria de sistemas" > "sistemas")
        encontrados.sort(key=lambda x: (x[0], -(x[1] - x[0])))
        detalles, ocupado = [], set()
        for inicio, fin, tipo, valor, span in encontrados:
            if ocupado & set(range(inicio, fin)):
                continue
            ocupado |= set(range(inicio, fin))
            detalles.append(Detalle(tipo=tipo, valor=valor, texto=span, fuente="lista"))
        normal = normalizar(texto)
        if not any(d.tipo == "facultad" for d in detalles) and re.search(r"\bingenieria\b", normal):
            ingenierias = [f["id"] for f in self.facultades if "Ingeniería" in f["nombre_oficial"]]
            detalles.append(Detalle(tipo="facultad", valor="", texto="ingenieria", fuente="lista",
                                    candidatos=ingenierias))
        return detalles

    # --- expresiones regulares -----------------------------------------------------------------
    def _regex(self, texto: str) -> list[Detalle]:
        normal = normalizar(texto)
        detalles = []
        if m := RE_PERIODO.search(texto):
            detalles.append(Detalle("periodo", f"{m.group(1)}-{m.group(2).upper()}", m.group(0), "regex"))
        elif m := RE_PERIODO_RELATIVO.search(normal):
            valor = "proximo_ciclo" if m.group(1) in {"proximo", "siguiente"} else "ciclo_actual"
            detalles.append(Detalle("periodo", valor, m.group(0), "regex"))
        if m := RE_VECES.search(normal):
            detalles.append(Detalle("veces", str(NUMEROS[m.group(1)]), m.group(0), "regex"))
        elif m := RE_VECES_ORDINAL.search(normal):
            detalles.append(Detalle("veces", str(ORDINALES[m.group(1)]), m.group(0), "regex"))
        if m := RE_CODIGO.search(texto):
            detalles.append(Detalle("codigo_estudiante", m.group(0), m.group(0), "regex"))
        if m := RE_CURSO_TRAS_VERBO.search(texto):
            detalles.append(Detalle("curso", m.group(1), m.group(1), "regex"))
        return detalles

    # --- spaCy NER -----------------------------------------------------------------------------
    def _spacy(self, texto: str) -> list[Detalle]:
        tipos = {"PER": "persona", "LOC": "lugar", "ORG": "organizacion"}
        # Una sola palabra al inicio de la oración suele ser un verbo con mayúscula («Desaprobé», «Quiero»)
        return [Detalle(tipos[e.label_], e.text, e.text, "spacy") for e in self.nlp(texto).ents
                if e.label_ in tipos and not (len(e) == 1 and e[0].is_sent_start)]

    def nombre(self, id_facultad: str) -> str:
        return self.nombre_facultad.get(id_facultad, id_facultad)


def _resolver_conflictos(detalles: list[Detalle]) -> list[Detalle]:
    """Un detalle por tipo (gana la fuente prioritaria). ORG/LOC de spaCy que repiten una facultad
    o un curso de la lista se descartan."""
    textos_lista = {normalizar(d.texto) for d in detalles if d.fuente == "lista"}
    elegidos: dict[str, Detalle] = {}
    for d in sorted(detalles, key=lambda d: -PRIORIDAD[d.fuente]):
        if d.fuente == "spacy" and any(t in normalizar(d.texto) or normalizar(d.texto) in t for t in textos_lista):
            continue
        if d.fuente == "spacy" and d.tipo in {"persona", "lugar", "organizacion"} and normalizar(d.texto) in {
                "fisi", "unmsm", "san marcos", "sum"}:
            continue
        # "Cálculo" capturado por la regex del verbo se normaliza con la lista de cursos si coincide
        if d.tipo == "curso" and "curso" in elegidos:
            continue
        elegidos.setdefault(d.tipo, d)
    return list(elegidos.values())


@lru_cache(maxsize=2)
def _spacy(dir_data):
    import spacy
    from spacy.matcher import PhraseMatcher

    nlp = spacy.load("es_core_news_sm")
    matcher = PhraseMatcher(nlp.vocab, attr="LOWER")
    valores: dict[str, tuple[str, str]] = {}

    def agregar(tipo: str, valor: str, frases: list[str]):
        clave = f"{tipo}:{valor}"
        valores[clave] = (tipo, valor)
        matcher.add(clave, [nlp.make_doc(normalizar(f)) for f in frases if f.strip()])

    ruta = dir_data / "entidades"
    with (ruta / "facultades.csv").open(encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            agregar("facultad", fila["id"], [fila["nombre_oficial"], fila["sigla"]] + fila["sinonimos"].split(";"))
    with (ruta / "tipos.csv").open(encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            agregar(fila["tipo"], fila["valor"], fila["sinonimos"].split(";"))
    with (ruta / "cursos.csv").open(encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            agregar("curso", fila["valor"], [fila["valor"]] + fila["sinonimos"].split(";"))
    return nlp, matcher, valores
