"""Construye las etapas del orquestador en el orden fijo de FR-002."""

from __future__ import annotations

ORDEN = ["pendiente", "reglas", "nlp_ml", "retrieval", "llm"]


def registrar_etapas(orq, etapas: list[str] | None = None) -> None:
    activas = [e for e in ORDEN if etapas is None or e in etapas]
    for nombre in activas:
        etapa = _construir(nombre, orq)
        if etapa is not None:
            orq.registrar(nombre, etapa)


def _construir(nombre: str, orq):
    if nombre == "reglas":
        from src import reglas

        return reglas.etapa(reglas.MotorReglas(orq.config))
    if nombre in {"pendiente", "nlp_ml"}:
        etapas = _etapas_nlp(orq)
        return etapas.pendiente if nombre == "pendiente" else etapas.nlp_ml
    if nombre == "retrieval":
        from src import recuperacion

        orq.indice = recuperacion.Indice.desde_archivos(orq.config)
        return recuperacion.etapa(orq.indice)
    if nombre == "llm":
        from src import llm

        return llm.etapa(orq)
    return None


def _etapas_nlp(orq):
    if getattr(orq, "_etapas_nlp", None) is None:
        from src import conocimiento, entidades, intenciones, politica

        orq.extractor = entidades.Extractor(orq.config)
        orq.modelo = intenciones.cargar_modelo(orq.config)
        orq.definiciones = politica.cargar_definiciones(orq.config)
        pasajes = {p.id: p for p in conocimiento.cargar_jsonl(orq.config.ruta("conocimiento", "pasajes.jsonl"))}
        orq._etapas_nlp = politica.EtapasNLP(orq, orq.extractor, orq.modelo, orq.definiciones, pasajes)
    return orq._etapas_nlp
