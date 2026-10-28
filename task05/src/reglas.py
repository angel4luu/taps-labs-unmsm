"""Componente 1 — Reglas: patrones fijos (saludo, ayuda, nombre, gracias, despedida) y guardarraíles."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

import yaml

from src.config import Config
from src.modelos import Componente, Politica, Respuesta, Sesion
from src.preprocesamiento import normalizar

# Palabras que pueden seguir a "soy ..." sin ser un nombre ("soy de la FISI", "soy estudiante")
NO_NOMBRES = {"de", "del", "la", "el", "un", "una", "estudiante", "alumno", "alumna", "cachimbo", "cachimba",
              "nuevo", "nueva", "egresado", "egresada", "ingresante", "de", "sanmarquino", "sanmarquina", "muy",
              "yo", "tu", "su"}


@dataclass
class Regla:
    nombre: str
    patrones: list[re.Pattern]
    respuestas: list[str]
    patrones_original: list[re.Pattern]
    max_palabras: int | None = None
    fin: bool = False
    guardarrail: bool = False

    def coincide(self, normalizado: str, original: str) -> re.Match | None:
        if self.max_palabras and len(normalizado.split()) > self.max_palabras:
            return None
        for patron in self.patrones:
            if m := patron.search(normalizado):
                return m
        for patron in self.patrones_original:
            if m := patron.search(original):
                return m
        return None


def _compilar(entrada: dict, guardarrail: bool) -> Regla:
    return Regla(
        nombre=entrada["nombre"],
        patrones=[re.compile(p) for p in entrada.get("patrones", [])],
        patrones_original=[re.compile(p) for p in entrada.get("patrones_original", [])],
        respuestas=entrada["respuestas"],
        max_palabras=entrada.get("max_palabras"),
        fin=entrada.get("fin", False),
        guardarrail=guardarrail,
    )


class MotorReglas:
    def __init__(self, config: Config | None = None, semilla: int = 42):
        self.config = config or Config()
        datos = yaml.safe_load(self.config.ruta("reglas", "patrones.yaml").read_text(encoding="utf-8"))
        # Orden fijo: guardarraíles primero (FR-007), luego el resto
        self.reglas = [_compilar(r, True) for r in datos["guardarrailes"]] + [
            _compilar(r, False) for r in datos["reglas"]
        ]
        self.menu = self._menu(datos.get("menu_respaldo", []))
        self._azar = random.Random(semilla)

    def _menu(self, respaldo: list[str]) -> list[str]:
        ruta = self.config.ruta("intenciones", "definicion.yaml")
        if not ruta.exists():
            return respaldo
        definiciones = yaml.safe_load(ruta.read_text(encoding="utf-8"))
        return [f"{d['descripcion']} — {d['ejemplo_menu']}" for tema, d in definiciones.items()
                if tema != "fuera_de_dominio"]

    def evaluar(self, texto: str, sesion: Sesion) -> Respuesta | None:
        normalizado = normalizar(texto)
        for regla in self.reglas:
            m = regla.coincide(normalizado, texto)
            if m is None:
                continue
            if regla.nombre == "nombre":
                capturado = m.group(1)
                if capturado in NO_NOMBRES:
                    continue
                sesion.nombre = capturado.capitalize()
            return self._respuesta(regla, sesion)
        return None

    def _respuesta(self, regla: Regla, sesion: Sesion) -> Respuesta:
        plantilla = self._azar.choice(regla.respuestas)
        texto = plantilla.format(nombre=f", {sesion.nombre}" if sesion.nombre else "",
                                 nombre_capturado=sesion.nombre or "")
        if regla.nombre == "ayuda":
            texto += "\n" + "\n".join(f"- {linea}" for linea in self.menu)
        politica = [Politica.RECHAZO] if regla.guardarrail else []
        if regla.fin:
            sesion.activa = False
        return Respuesta(texto=texto, componente=Componente.REGLAS, regla=regla.nombre, politica=politica,
                         fin_conversacion=regla.fin)


def etapa(motor: MotorReglas):
    def _etapa(mensaje, sesion, contexto):
        return motor.evaluar(mensaje.texto_original, sesion)

    return _etapa
