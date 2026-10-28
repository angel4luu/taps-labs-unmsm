"""Rutas, umbrales y ajustes del LLM. Único lugar a editar para cambiar el comportamiento."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
DIR_DATA = RAIZ / "data"
DIR_RAW = DIR_DATA / "raw"
DIR_CONOCIMIENTO = DIR_DATA / "conocimiento"
DIR_INTENCIONES = DIR_DATA / "intenciones"
DIR_ENTIDADES = DIR_DATA / "entidades"
DIR_REGLAS = DIR_DATA / "reglas"
DIR_EVALUACION_DATOS = DIR_DATA / "evaluacion"
DIR_MODELOS = RAIZ / "modelos"
DIR_EVIDENCIA = RAIZ / "evidencia"
DIR_EVALUACION = DIR_EVIDENCIA / "evaluacion"
DIR_FLUJOS = DIR_EVIDENCIA / "flujos"
DIR_CAPTURAS = DIR_EVIDENCIA / "capturas"
DIR_ENTREGABLES = RAIZ / "entregables"

REPORTE_EVALUACION = DIR_EVALUACION / "reporte.json"

load_dotenv(RAIZ / ".env")


def hay_credencial_online() -> bool:
    """Solo comprueba si la clave está definida; nunca la guarda, registra ni imprime."""
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def _umbrales_ajustados() -> dict:
    try:
        return json.loads(REPORTE_EVALUACION.read_text(encoding="utf-8")).get("umbrales", {})
    except (OSError, ValueError):
        return {}


@dataclass
class Config:
    dir_data: Path = DIR_DATA
    LLM_MODELO: str = field(default_factory=lambda: os.environ.get("CHATBOT_LLM_MODEL", "gemini-3.8-flash"))
    LLM_THINKING_LEVEL: str = "low"
    LLM_MODO: str = field(default_factory=lambda: os.environ.get("CHATBOT_LLM_MODO", "auto"))  # auto|online|offline
    # Modelo local opcional para el modo sin conexión (p. ej. "Qwen/Qwen2.5-0.5B-Instruct", ~1 GB).
    # Vacío por defecto: sin conexión se cita el artículo textual, sin descargas extra.
    LLM_LOCAL_MODELO: str = field(default_factory=lambda: os.environ.get("CHATBOT_LLM_LOCAL", ""))
    LLM_TIMEOUT_ONLINE_S: int = 20
    LLM_TIMEOUT_LOCAL_S: int = 15
    UMBRAL_ACEPTAR: float = 0.60
    UMBRAL_RECHAZAR: float = 0.35
    UMBRAL_FAQ: float = 0.35
    UMBRAL_CONTEXTO: float = 0.15
    HISTORIAL_TURNOS: int = 6
    MAX_CARACTERES: int = 1000
    SEMILLA: int = 42

    def __post_init__(self) -> None:
        ajustados = _umbrales_ajustados()
        self.UMBRAL_ACEPTAR = ajustados.get("aceptar", self.UMBRAL_ACEPTAR)
        self.UMBRAL_RECHAZAR = ajustados.get("rechazar", self.UMBRAL_RECHAZAR)
        self.UMBRAL_FAQ = ajustados.get("faq", self.UMBRAL_FAQ)
        self.UMBRAL_CONTEXTO = ajustados.get("contexto", self.UMBRAL_CONTEXTO)

    def ruta(self, *partes: str) -> Path:
        return self.dir_data.joinpath(*partes)
