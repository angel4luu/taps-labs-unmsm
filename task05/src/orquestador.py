"""Orquestador híbrido: cada mensaje recorre pendiente → reglas → nlp_ml → retrieval → llm (FR-002)."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Callable

from src import preprocesamiento
from src.config import Config
from src.modelos import (
    Componente,
    Detalle,
    EntradaConocimiento,
    Mensaje,
    Respuesta,
    ResultadoIntencion,
    Sesion,
)

NO_ENTENDI = "No entendí tu consulta. Escribe *ayuda* para ver los temas con los que puedo ayudarte."
VACIO = "Escribe tu pregunta, por favor."
CERRADA = "La conversación terminó. Inicia una nueva sesión para empezar otra."
ERROR_INTERNO = "Lo siento, tuve un problema interno al procesar tu mensaje. ¿Puedes intentarlo de nuevo?"


@dataclass
class Contexto:
    """Lo que cada etapa deja a las siguientes dentro del mismo turno."""

    tema: str | None = None
    resultado: ResultadoIntencion | None = None
    detalles: list[Detalle] = field(default_factory=list)
    pasajes: list[EntradaConocimiento] = field(default_factory=list)
    politica: list = field(default_factory=list)
    accion: str | None = None
    preferir_llm: bool = False
    forzar_offline: bool = False
    intencion_forzada: str | None = None  # tema confirmado por el estudiante o ya decidido antes
    omitir_requeridos: bool = False  # tras pedir un detalle dos veces se responde en general
    seguimiento: bool = False  # "¿y si…?" continúa el tema del turno anterior
    nota: str | None = None  # aviso adicional al final de la respuesta


Etapa = Callable[[Mensaje, Sesion, Contexto], "Respuesta | None"]


class Orquestador:
    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.etapas: list[tuple[str, Etapa]] = []
        self.forzar_offline = False

    @classmethod
    def cargar(cls, config: Config | None = None, etapas: list[str] | None = None) -> "Orquestador":
        """Carga los componentes disponibles en el orden fijo. `etapas` limita cuáles se registran."""
        orq = cls(config)
        from src import registro

        registro.registrar_etapas(orq, etapas)
        return orq

    def registrar(self, nombre: str, etapa: Etapa) -> None:
        self.etapas.append((nombre, etapa))

    def nueva_sesion(self) -> Sesion:
        return Sesion()

    def responder(self, texto: str, sesion: Sesion) -> Respuesta:
        inicio = time.perf_counter()
        mensaje = preprocesamiento.procesar(texto, turno=len(sesion.historial) + 1,
                                            max_caracteres=self.config.MAX_CARACTERES)
        respuesta = self._responder(mensaje, sesion)
        respuesta.latencia_ms = int((time.perf_counter() - inicio) * 1000)
        sesion.historial.append((mensaje, respuesta))
        return respuesta

    def reprocesar(self, mensaje: Mensaje, sesion: Sesion, intencion_forzada: str | None = None,
                   omitir_requeridos: bool = False) -> Respuesta:
        """Vuelve a procesar el mensaje original cuando el estudiante responde una pregunta pendiente."""
        return self._responder(mensaje, sesion, Contexto(forzar_offline=self.forzar_offline,
                                                         intencion_forzada=intencion_forzada,
                                                         omitir_requeridos=omitir_requeridos))

    def _responder(self, mensaje: Mensaje, sesion: Sesion, contexto: Contexto | None = None) -> Respuesta:
        if not sesion.activa:
            return Respuesta(texto=CERRADA, componente=Componente.REGLAS, regla="sesion_cerrada")
        if not re.search(r"[a-zA-Z0-9áéíóúñÁÉÍÓÚÑ]", mensaje.texto_original):
            return Respuesta(texto=VACIO, componente=Componente.REGLAS, regla="vacio")
        contexto = contexto or Contexto(forzar_offline=self.forzar_offline)
        for nombre, etapa in self.etapas:
            if contexto.intencion_forzada and nombre in {"pendiente", "reglas"}:
                continue
            try:
                respuesta = etapa(mensaje, sesion, contexto)
            except Exception as error:  # el chat nunca se cae por un componente
                return Respuesta(texto=f"{ERROR_INTERNO} ({nombre}: {type(error).__name__})",
                                 componente=Componente.FALLBACK_EXTRACTIVO)
            if respuesta is not None:
                if respuesta.intencion is None:
                    respuesta.intencion = contexto.resultado
                if not respuesta.detalles:
                    respuesta.detalles = contexto.detalles
                for politica in contexto.politica:
                    if politica not in respuesta.politica:
                        respuesta.politica.append(politica)
                if contexto.nota and respuesta.componente != Componente.REGLAS:
                    respuesta.texto += f"\n\n{contexto.nota}"
                return respuesta
        return Respuesta(texto=NO_ENTENDI, componente=Componente.REGLAS, regla="sin_respuesta",
                         intencion=contexto.resultado, detalles=contexto.detalles)
