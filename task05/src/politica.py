"""Política de decisión del componente NLP/ML: bandas de confianza, detalles requeridos, preguntas
pendientes (pedir un detalle o confirmar el tema) y memoria de sesión."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

from src.config import Config
from src.modelos import (
    Accion,
    Componente,
    Detalle,
    EntradaConocimiento,
    Fuente,
    Intencion,
    Pendiente,
    Politica,
    Respuesta,
    ResultadoIntencion,
    Sesion,
)
from src.preprocesamiento import normalizar

FUERA_DE_DOMINIO = ("Solo puedo ayudarte con consultas académicas de pregrado de la UNMSM: matrícula, repitencia, "
                    "reserva y retiro, créditos, grados y títulos, trámites, calendario, bienestar y biblioteca. "
                    "Escribe *ayuda* para ver ejemplos.")
TIPOS_PERSONALES = {"curso", "veces", "facultad", "periodo"}
RE_SEGUIMIENTO = re.compile(r"^(y|e|entonces|pero|tambien|ademas|osea|o sea)\b")


@dataclass
class Decision:
    banda: str  # aceptar | confirmar | sin_filtro
    accion: str | None = None
    faltante: str | None = None
    pregunta: str | None = None
    filtro_tema: str | None = None
    uso_memoria: bool = False
    opciones: list[str] = field(default_factory=list)


def cargar_definiciones(config: Config | None = None) -> dict[str, Intencion]:
    config = config or Config()
    datos = yaml.safe_load(config.ruta("intenciones", "definicion.yaml").read_text(encoding="utf-8"))
    return {tema: Intencion(id=tema, descripcion=d["descripcion"], ejemplo_menu=d["ejemplo_menu"],
                            requeridos=d.get("requeridos", []), opcionales=d.get("opcionales", []),
                            accion=Accion(d["accion"]), plantilla=d.get("plantilla"),
                            pregunta_detalle=d.get("pregunta_detalle", {}))
            for tema, d in datos.items()}


def opciones_confirmacion(resultado: ResultadoIntencion) -> list[str]:
    """Los dos temas más probables que el estudiante puede elegir (nunca «fuera de dominio»)."""
    return [t for t, _ in resultado.top2 if t != "fuera_de_dominio"][:2]


def banda(confianza: float, aceptar: float, rechazar: float) -> str:
    if confianza >= aceptar:
        return "aceptar"
    if confianza >= rechazar:
        return "confirmar"
    return "sin_filtro"


def decidir(resultado: ResultadoIntencion, detalles: list[Detalle], sesion: Sesion,
            definiciones: dict[str, Intencion], aceptar: float, rechazar: float,
            omitir_requeridos: bool = False) -> Decision:
    b = resultado.banda if resultado.banda == "aceptar" else banda(resultado.confianza, aceptar, rechazar)
    if b == "confirmar" and len(opciones_confirmacion(resultado)) < 2:
        b = "sin_filtro"  # no hay dos temas válidos que ofrecer
    if b == "confirmar":
        opciones = opciones_confirmacion(resultado)
        nombres = [definiciones[t].descripcion.lower() for t in opciones]
        return Decision(banda=b, opciones=opciones,
                        pregunta=f"¿Tu consulta es sobre **{nombres[0]}** o sobre **{nombres[1]}**? "
                                 f"Responde con el tema (o con 1 / 2).")
    if b == "sin_filtro":
        return Decision(banda=b)
    definicion = definiciones[resultado.intencion]
    decision = Decision(banda=b, accion=definicion.accion.value, filtro_tema=resultado.intencion)
    if resultado.intencion == "fuera_de_dominio" or omitir_requeridos:
        return decision
    presentes = {d.tipo: d for d in detalles}
    for requerido in definicion.requeridos:
        detalle = presentes.get(requerido)
        if detalle and detalle.valor:
            continue
        if detalle and detalle.candidatos:  # facultad ambigua ("Ingeniería")
            decision.faltante, decision.opciones = requerido, detalle.candidatos
            decision.pregunta = None  # se arma con los nombres en la etapa
            return decision
        if requerido in sesion.detalles_memoria:
            decision.uso_memoria = True
            continue
        decision.faltante = requerido
        decision.pregunta = definicion.pregunta_detalle.get(requerido, f"¿Me indicas tu {requerido}?")
        return decision
    return decision


def es_seguimiento(texto: str) -> bool:
    normal = normalizar(texto)
    return bool(RE_SEGUIMIENTO.match(normal)) and len(normal.split()) <= 10


def personalizada(texto: str, detalles: list[Detalle]) -> bool:
    """Preguntas con detalles propios, de varias partes o largas: mejor una respuesta redactada (LLM)."""
    return (any(d.tipo in TIPOS_PERSONALES and d.valor for d in detalles) or texto.count("?") > 1
            or len(texto.split()) > 18)


class EtapasNLP:
    """Etapas `pendiente` y `nlp_ml` del orquestador."""

    def __init__(self, orq, extractor, modelo, definiciones: dict[str, Intencion],
                 pasajes: dict[str, EntradaConocimiento]):
        self.orq, self.extractor, self.modelo = orq, extractor, modelo
        self.definiciones, self.pasajes = definiciones, pasajes

    # --- etapa 0: respuesta a una pregunta pendiente ---------------------------------------------------
    def pendiente(self, mensaje, sesion: Sesion, contexto):
        p = sesion.pendiente
        if p is None:
            return None
        if p.tipo == "confirmacion":
            elegido = self._elegir_tema(mensaje.texto_original, p.opciones)
            sesion.pendiente = None
            if elegido is None:
                return None  # no eligió: se trata como un mensaje nuevo
            return self.orq.reprocesar(p.mensaje_original, sesion, intencion_forzada=elegido)
        # tipo detalle
        detalle = self._detalle_respondido(mensaje.texto_original, p)
        if detalle is not None:
            sesion.recordar(detalle)
            sesion.pendiente = None
            respuesta = self.orq.reprocesar(p.mensaje_original, sesion, intencion_forzada=p.intencion)
            if Politica.MEMORIA_SESION not in respuesta.politica:
                respuesta.politica.append(Politica.MEMORIA_SESION)
            return respuesta
        if len(mensaje.texto_normalizado.split()) >= 4:  # parece una pregunta nueva
            sesion.pendiente = None
            return None
        if p.intentos == 0:
            p.intentos = 1
            return Respuesta(texto=f"No reconocí la {p.faltante} en tu respuesta. {self._pregunta(p.faltante, p)}",
                             componente=Componente.NLP_ML, politica=[Politica.PEDIR_DETALLE])
        sesion.pendiente = None
        respuesta = self.orq.reprocesar(p.mensaje_original, sesion, intencion_forzada=p.intencion,
                                        omitir_requeridos=True)
        respuesta.texto = f"Te doy una respuesta general (sin {p.faltante}):\n\n{respuesta.texto}"
        return respuesta

    def _elegir_tema(self, texto: str, opciones: list[str]) -> str | None:
        normal = normalizar(texto)
        if normal in {"1", "2"}:
            return opciones[int(normal) - 1]
        for tema in opciones:
            nombres = {normalizar(tema.replace("_", " ")), normalizar(self.definiciones[tema].descripcion)}
            nombres |= {normalizar(p) for p in self.definiciones[tema].descripcion.split() if len(p) > 4}
            if any(n and n in normal for n in nombres):
                return tema
        return None

    def _detalle_respondido(self, texto: str, p: Pendiente) -> Detalle | None:
        for d in self.extractor.extraer(texto):
            if d.tipo == p.faltante and d.valor and (not p.opciones or d.valor in p.opciones):
                return d
        if p.opciones:  # elige entre candidatos por sigla o nombre
            normal = normalizar(texto)
            for id_ in p.opciones:
                if normalizar(id_) in normal.split() or normalizar(self.extractor.nombre(id_)) in normal:
                    return Detalle(p.faltante, id_, texto, "lista")
        return None

    def _pregunta(self, faltante: str, p: Pendiente) -> str:
        if p.opciones:
            nombres = "; ".join(f"{self.extractor.nombre(o)} ({o})" for o in p.opciones)
            return f"¿Cuál de estas facultades? {nombres}"
        definicion = self.definiciones.get(p.intencion)
        return (definicion.pregunta_detalle.get(faltante) if definicion else None) or f"¿Me indicas tu {faltante}?"

    # --- etapa 2: intención + detalles + política --------------------------------------------------------
    def nlp_ml(self, mensaje, sesion: Sesion, contexto):
        cfg = self.orq.config
        detalles = self.extractor.extraer(mensaje.texto_original)
        resultado = self._resultado(mensaje, sesion, contexto)
        decision = decidir(resultado, detalles, sesion, self.definiciones, cfg.UMBRAL_ACEPTAR, cfg.UMBRAL_RECHAZAR,
                           contexto.omitir_requeridos)
        resultado.banda = decision.banda
        for d in detalles:
            sesion.recordar(d)
        efectivos = {**{t: d for t, d in sesion.detalles_memoria.items()}, **{d.tipo: d for d in detalles}}
        contexto.resultado, contexto.detalles = resultado, list(efectivos.values())

        if decision.banda == "confirmar":
            sesion.pendiente = Pendiente(tipo="confirmacion", mensaje_original=mensaje, opciones=decision.opciones)
            return Respuesta(texto=decision.pregunta, componente=Componente.NLP_ML, politica=[Politica.CONFIRMAR_TOP2])
        if decision.banda == "sin_filtro":
            contexto.politica.append(Politica.SIN_FILTRO)
            return None
        if resultado.intencion == "fuera_de_dominio":
            return Respuesta(texto=FUERA_DE_DOMINIO, componente=Componente.NLP_ML, politica=[Politica.FUERA_DOMINIO])
        if decision.faltante:
            sesion.pendiente = Pendiente(tipo="detalle", mensaje_original=mensaje, intencion=resultado.intencion,
                                         faltante=decision.faltante, opciones=decision.opciones)
            return Respuesta(texto=decision.pregunta or self._pregunta(decision.faltante, sesion.pendiente),
                             componente=Componente.NLP_ML, politica=[Politica.PEDIR_DETALLE])
        if decision.uso_memoria:
            contexto.politica.append(Politica.MEMORIA_SESION)
        self._nota_segundo_tema(resultado, contexto)
        if decision.accion == Accion.PLANTILLA.value:
            return self._plantilla(resultado.intencion, contexto)
        contexto.tema = resultado.intencion
        contexto.accion = decision.accion
        contexto.preferir_llm = (decision.accion == Accion.RETRIEVAL_LLM.value and
                                 (contexto.seguimiento or personalizada(mensaje.texto_original, detalles)))
        return None

    def _resultado(self, mensaje, sesion: Sesion, contexto) -> ResultadoIntencion:
        if contexto.intencion_forzada:
            return ResultadoIntencion(contexto.intencion_forzada, 1.0, [(contexto.intencion_forzada, 1.0)],
                                      "confirmado por el estudiante", "aceptar")
        anterior = next((r.intencion for _, r in reversed(sesion.historial) if r.intencion), None)
        if es_seguimiento(mensaje.texto_original) and anterior and anterior.intencion != "fuera_de_dominio":
            contexto.seguimiento = True
            return ResultadoIntencion(anterior.intencion, anterior.confianza, anterior.top2,
                                      "seguimiento del turno anterior", "aceptar")
        return self.modelo.predecir(mensaje)

    def _nota_segundo_tema(self, resultado: ResultadoIntencion, contexto) -> None:
        """Mensajes con dos temas: se responde el principal y se ofrece el segundo."""
        if len(resultado.top2) > 1:
            tema2, conf2 = resultado.top2[1]
            if conf2 >= 0.30 and tema2 not in {resultado.intencion, "fuera_de_dominio"}:
                contexto.nota = f"También puedo ayudarte con {self.definiciones[tema2].descripcion.lower()} después."

    def _plantilla(self, tema: str, contexto) -> Respuesta:
        definicion = self.definiciones[tema]
        detalles = {d.tipo: d for d in contexto.detalles}
        facultad = detalles.get("facultad")
        periodo = detalles.get("periodo")
        periodo_txt = ""
        if periodo and periodo.valor not in {"proximo_ciclo", "ciclo_actual"}:
            periodo_txt = f" del periodo {periodo.valor}"
        elif periodo:
            periodo_txt = " del próximo ciclo" if periodo.valor == "proximo_ciclo" else " del ciclo actual"
        texto = " ".join(definicion.plantilla.split()).format(
            facultad_nombre=self.extractor.nombre(facultad.valor) if facultad else "tu facultad",
            periodo_txt=periodo_txt)
        fuentes, recordatorio = [], None
        pasaje = self.pasajes.get("matricula-2026-art-05")
        if pasaje:
            fuentes.append(Fuente(pasaje.id, pasaje.documento, pasaje.ubicacion))
            recordatorio = (f"Información referencial (fuente: {pasaje.fecha_fuente}). Confirma las fechas en "
                            f"{pasaje.oficina}.")
        return Respuesta(texto=texto, componente=Componente.NLP_ML, fuentes=fuentes,
                         recordatorio_referencial=recordatorio)
