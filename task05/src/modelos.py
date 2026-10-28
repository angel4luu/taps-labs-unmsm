"""Tipos compartidos por todos los componentes (ver specs/.../data-model.md)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Componente(str, Enum):
    REGLAS = "Reglas"
    NLP_ML = "NLP/ML"
    RETRIEVAL = "Retrieval"
    LLM = "LLM"
    LLM_LOCAL = "LLM local (fallback)"
    FALLBACK_EXTRACTIVO = "Fallback extractivo"


class Politica(str, Enum):
    NINGUNA = "Ninguna"
    PEDIR_DETALLE = "Pide detalle"
    CONFIRMAR_TOP2 = "Confirma tema"
    RECHAZO = "Rechazo"
    FUERA_DOMINIO = "Fuera de dominio"
    MEMORIA_SESION = "Memoria de sesión"
    FALLBACK_OFFLINE = "Fallback offline"
    SIN_FILTRO = "Sin filtro"


class Accion(str, Enum):
    PLANTILLA = "PLANTILLA"
    RETRIEVAL = "RETRIEVAL"
    RETRIEVAL_LLM = "RETRIEVAL_LLM"
    RECHAZO_CORTES = "RECHAZO_CORTES"


class Tema(str, Enum):
    MATRICULA = "matricula"
    RESERVA_RETIRO = "reserva_retiro"
    REPITENCIA = "repitencia"
    CREDITOS_CURSOS = "creditos_cursos"
    GRADOS_TITULOS = "grados_titulos"
    TRAMITES = "tramites"
    CALENDARIO = "calendario"
    BIENESTAR = "bienestar"
    BIBLIOTECA = "biblioteca"
    FUERA_DE_DOMINIO = "fuera_de_dominio"


TEMAS = [t.value for t in Tema]


@dataclass
class Mensaje:
    texto_original: str  # 1–1000 caracteres tras truncar
    texto_normalizado: str
    tokens: list[str]
    turno: int = 0


@dataclass
class Detalle:
    tipo: str  # facultad, periodo, curso, veces, tipo_tramite, grado, persona, lugar, codigo_estudiante
    valor: str
    texto: str
    fuente: str  # regex | lista | spacy
    candidatos: list[str] = field(default_factory=list)

    def etiqueta(self) -> str:
        if self.candidatos and not self.valor:
            return f"{self.tipo}=?({'/'.join(self.candidatos)})"
        return f"{self.tipo}={self.valor}"


@dataclass
class Intencion:
    id: str
    descripcion: str
    ejemplo_menu: str
    requeridos: list[str]
    opcionales: list[str]
    accion: Accion
    plantilla: str | None = None
    pregunta_detalle: dict[str, str] = field(default_factory=dict)


@dataclass
class EntradaConocimiento:
    id: str
    tipo: str  # faq | pasaje
    tema: str
    texto: str
    documento: str
    ubicacion: str
    pregunta: str | None = None
    alternativas: list[str] = field(default_factory=list)  # otras formas de hacer la misma pregunta (FAQ)
    url: str | None = None
    fecha_fuente: date | str | None = None
    referencial: bool = False
    oficina: str | None = None

    def referencia(self) -> str:
        return f"{self.documento} — {self.ubicacion}"


@dataclass
class ResultadoIntencion:
    intencion: str
    confianza: float
    top2: list[tuple[str, float]]
    modelo: str
    banda: str  # aceptar | confirmar | sin_filtro


@dataclass
class Fuente:
    id: str
    documento: str
    ubicacion: str
    score: float | None = None
    cita: str | None = None

    def texto(self) -> str:
        s = f"{self.documento} — {self.ubicacion}"
        return f"{s} ({self.score:.2f})" if self.score is not None else s


@dataclass
class Respuesta:
    texto: str
    componente: Componente
    politica: list[Politica] = field(default_factory=list)
    regla: str | None = None
    intencion: ResultadoIntencion | None = None
    detalles: list[Detalle] = field(default_factory=list)
    fuentes: list[Fuente] = field(default_factory=list)
    recordatorio_referencial: str | None = None
    latencia_ms: int = 0
    fin_conversacion: bool = False


@dataclass
class Pendiente:
    tipo: str  # detalle | confirmacion
    mensaje_original: Mensaje
    intencion: str | None = None
    faltante: str | None = None
    opciones: list[str] = field(default_factory=list)
    intentos: int = 0  # 0–1


@dataclass
class Sesion:
    nombre: str | None = None
    detalles_memoria: dict[str, Detalle] = field(default_factory=dict)
    historial: list[tuple[Mensaje, Respuesta]] = field(default_factory=list)
    pendiente: Pendiente | None = None
    activa: bool = True

    def recordar(self, detalle: Detalle) -> None:
        # Nunca se guardan códigos ni datos personales; gana el último valor de cada tipo
        if detalle.tipo in {"codigo_estudiante", "persona"} or not detalle.valor:
            return
        self.detalles_memoria[detalle.tipo] = detalle
