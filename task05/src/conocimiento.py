"""Base de conocimiento: descarga los PDF oficiales y los divide en pasajes por artículo."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

import requests
import yaml
from pypdf import PdfReader

from src.config import Config
from src.modelos import TEMAS, EntradaConocimiento

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
MAX_PALABRAS = 350
MIN_PALABRAS_PASAJE, MAX_PALABRAS_PASAJE = 20, 400

# Tema de cada artículo del Reglamento de Matrícula 2026 (asignado tras leer el texto)
TEMA_ARTICULO = {
    4: "calendario", 5: "calendario", 10: "matricula", 11: "matricula", 12: "repitencia",
    14: "calendario", 16: "matricula", 18: "repitencia", 19: "repitencia", 20: "repitencia",
    21: "tramites", 22: "tramites", 23: "tramites", 24: "matricula", 25: "matricula",
    26: "creditos_cursos", 27: "creditos_cursos", 28: "creditos_cursos", 29: "creditos_cursos",
    30: "reserva_retiro", 31: "reserva_retiro", 32: "reserva_retiro", 33: "reserva_retiro",
    34: "calendario", 35: "matricula", 36: "tramites", 37: "tramites",
}
# El Art. 13 (definiciones) cubre muchos temas: se divide por literal
TEMA_ART13 = {
    "a": "matricula", "b": "matricula", "c": "repitencia", "d": "creditos_cursos", "e": "reserva_retiro",
    "f": "reserva_retiro", "g": "matricula", "h": "reserva_retiro", "i": "reserva_retiro",
    "j": "reserva_retiro", "k": "reserva_retiro", "l": "repitencia", "m": "creditos_cursos",
    "n": "repitencia", "o": "repitencia", "p": "creditos_cursos", "q": "tramites", "r": "tramites",
    "s": "tramites", "t": "tramites", "u": "tramites", "v": "tramites", "w": "grados_titulos",
    "x": "creditos_cursos", "y": "creditos_cursos", "z": "creditos_cursos", "aa": "creditos_cursos",
    "bb": "tramites", "cc": "creditos_cursos",
}
TEMA_DISPOSICION = {"transitoria-primera": "reserva_retiro", "transitoria-segunda": "reserva_retiro",
                    "final-primera": "tramites"}

# Líneas que el PDF repite en cada página (firmas digitales, sello de autenticidad, pie de página)
RUIDO = [
    r"Firmado digitalmente por.*", r"^[A-ZÁÉÍÓÚÑ ]+ (Jose Felix|Christian Alberto|Jeri Gloria|Elsa)?\s*FAU.*$",
    r"^.*20148092282 (hard|soft).*$", r"^Motivo:.*$", r"^Fecha: \d{2}\.\d{2}\.\d{4}.*$",
    r"^(MANCHEGO|QUISPEZ|RUFFNER|MARCHINARES|PALOMINO|UBILLAS).*$", r"^\s*\d{1,2}\s*$",
]


def descargar(fuente: dict, config: Config) -> Path | None:
    if "url" not in fuente or fuente.get("pasajes_manuales"):
        return None
    destino = config.ruta("raw", f"{fuente['id']}.pdf")
    if destino.exists() and destino.stat().st_size > 0:
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    respuesta = requests.get(fuente["url"], headers={"User-Agent": USER_AGENT}, timeout=60)
    respuesta.raise_for_status()
    destino.write_bytes(respuesta.content)
    return destino


def limpiar(texto: str) -> str:
    lineas = []
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea or any(re.search(p, linea) for p in RUIDO):
            continue
        lineas.append(linea)
    return "\n".join(lineas)


def _texto_pdf(pdf: Path) -> str:
    """pdftotext (poppler) da texto limpio; pypdf en modo layout es el respaldo."""
    if shutil.which("pdftotext"):
        salida = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True)
        return salida.stdout
    paginas = PdfReader(str(pdf)).pages
    return "\n".join(re.sub(r" {2,}", " ", p.extract_text(extraction_mode="layout") or "") for p in paginas)


def extraer_texto(pdf: Path) -> str:
    texto = limpiar(_texto_pdf(pdf))
    # El sello "Esta es una copia auténtica..." se intercala en las dos primeras páginas
    texto = re.sub(r"Esta\s+es\s+una\s+copia\s+auténtica.*?verificación:\s*\w+", " ", texto, flags=re.S)
    return texto


def _compactar(texto: str) -> str:
    texto = re.sub(r"[\uf0b7\uf0a7\uf0d8\u2022\u25aa]", "-", texto).replace("\u00ad", "")
    texto = re.sub(r"-\n(?=[a-záéíóúñ])", "", texto)  # palabras partidas al final de línea
    return re.sub(r"\s+", " ", texto).strip()


def _palabras(texto: str) -> int:
    return len(texto.split())


def _partir_largo(texto: str, base_id: str, base_ubic: str) -> list[tuple[str, str, str]]:
    """Parte un artículo largo por incisos (a), b)… o i., ii.…) en trozos de hasta ~MAX_PALABRAS."""
    if _palabras(texto) <= MAX_PALABRAS:
        return [(base_id, base_ubic, texto)]
    # incisos a) · (i) · i. · viñetas "- " · numerales "1. " del anexo
    piezas = re.split(r"(?=\s(?:[a-z]\)|\([ivx]+\)|[ivx]+\.|-|\d\.)\s(?=\S))", texto)
    trozos, actual = [], ""
    for pieza in piezas:
        if actual and _palabras(actual) + _palabras(pieza) > MAX_PALABRAS:
            trozos.append(actual.strip())
            actual = pieza
        else:
            actual += pieza
    if actual.strip():
        trozos.append(actual.strip())
    if len(trozos) == 1:
        return [(base_id, base_ubic, texto)]
    return [(f"{base_id}-{k}", f"{base_ubic} (parte {k})", t) for k, t in enumerate(trozos, start=1)]


def dividir_articulos(texto: str, fuente: dict) -> list[EntradaConocimiento]:
    """Divide el texto en pasajes por artículo; el Art. 13 se divide por literal."""
    inicio = re.search(r"REGLAMENTO GENERAL DE MATR[ÍI]CULA PARA PREGRADO\s*\n\s*T[ÍI]TULO I", texto)
    cuerpo = texto[inicio.start():] if inicio else texto
    fin_anexos = re.search(r"ANEXO 02", cuerpo)
    cuerpo = cuerpo[: fin_anexos.start()] if fin_anexos else cuerpo
    anexo = re.search(r"ANEXO 01", cuerpo)
    anexo_txt = cuerpo[anexo.start():] if anexo else ""
    cuerpo = cuerpo[: anexo.start()] if anexo else cuerpo
    disp = re.search(r"T[ÍI]TULO III\s*\n?\s*DISPOSICIONES TRANSITORIAS", cuerpo)
    disp_txt = cuerpo[disp.start():] if disp else ""
    cuerpo = cuerpo[: disp.start()] if disp else cuerpo

    excluidos = set(fuente.get("excluir_articulos", []))
    partes = re.split(r"Art[íi]culo\s+(\d+)\s*[°º]", cuerpo)
    entradas: list[EntradaConocimiento] = []
    corto = None
    for i in range(1, len(partes), 2):
        numero, contenido = int(partes[i]), partes[i + 1]
        # Encabezados de título/capítulo que quedan al final del artículo anterior
        contenido = re.split(r"\n\s*(?:T[ÍI]TULO [IVX]+|CAP[ÍI]TULO [IVX]+|DISPOSICIONES GENERALES)\b", contenido)[0]
        if numero in excluidos:
            continue
        if numero == 13:
            entradas += _art13(contenido, fuente)
            continue
        tema = TEMA_ARTICULO.get(numero)
        if tema is None:
            continue
        texto_art = _compactar(f"Artículo {numero}° {contenido}")
        if corto is not None:  # artículo anterior demasiado corto: se une a este
            numero_corto, tema, texto_corto = corto
            texto_art, corto = f"{texto_corto} {texto_art}", None
            id_base, ubic_base = f"{fuente['id']}-art-{numero_corto:02d}-{numero:02d}", f"Arts. {numero_corto}–{numero}"
        else:
            id_base, ubic_base = f"{fuente['id']}-art-{numero:02d}", f"Art. {numero}"
        if _palabras(texto_art) < MIN_PALABRAS_PASAJE:
            corto = (numero, tema, texto_art)
            continue
        for id_, ubic, trozo in _partir_largo(texto_art, id_base, ubic_base):
            entradas.append(_entrada(id_, tema, trozo, ubic, fuente))

    if fuente.get("incluir_disposiciones") and disp_txt:
        entradas += _disposiciones(disp_txt, fuente)
    if fuente.get("incluir_anexo_01") and anexo_txt:
        texto_anexo = _compactar(anexo_txt)
        for id_, ubic, trozo in _partir_largo(texto_anexo, f"{fuente['id']}-anexo-01", "Anexo 01 (Jurado Ad Hoc)"):
            entradas.append(_entrada(id_, "repitencia", trozo, ubic, fuente))
    return entradas


def _art13(contenido: str, fuente: dict) -> list[EntradaConocimiento]:
    # Literales a) … cc) al inicio de línea; los incisos internos de o) también usan a) b) c),
    # por eso se toma la primera aparición de cada letra en orden.
    entradas = []
    marcas = list(re.finditer(r"(?m)^\s*([a-z]{1,2})\)\s", contenido))
    vistas, posiciones = set(), []
    orden = list(TEMA_ART13)
    siguiente = 0
    for m in marcas:
        letra = m.group(1)
        if siguiente < len(orden) and letra == orden[siguiente] and letra not in vistas:
            vistas.add(letra)
            posiciones.append((letra, m.start()))
            siguiente += 1
    for k, (letra, pos) in enumerate(posiciones):
        fin = posiciones[k + 1][1] if k + 1 < len(posiciones) else len(contenido)
        texto = _compactar(f"Artículo 13°, literal {letra}) {contenido[pos:fin].split(')', 1)[1]}")
        for id_, ubic, trozo in _partir_largo(texto, f"{fuente['id']}-art-13-{letra}", f"Art. 13, lit. {letra}"):
            entradas.append(_entrada(id_, TEMA_ART13[letra], trozo, ubic, fuente))
    return entradas


def _disposiciones(texto: str, fuente: dict) -> list[EntradaConocimiento]:
    entradas = []
    transitorias = re.search(r"DISPOSICI[ÓO]N TRANSITORIA(.*?)DISPOSICIONES FINALES", texto, flags=re.S)
    finales = re.search(r"DISPOSICIONES FINALES(.*)", texto, flags=re.S)
    for grupo, bloque in (("transitoria", transitorias), ("final", finales)):
        if not bloque:
            continue
        for m in re.finditer(r"(PRIMERA|SEGUNDA):\s*(.*?)(?=(?:SEGUNDA|TERCERA):|$)", bloque.group(1), flags=re.S):
            clave = f"{grupo}-{m.group(1).lower()}"
            if clave not in TEMA_DISPOSICION:
                continue
            ubic = f"Disposición {grupo} {m.group(1).lower()}"
            entradas.append(_entrada(f"{fuente['id']}-disp-{clave}", TEMA_DISPOSICION[clave],
                                     _compactar(f"{ubic.capitalize()}: {m.group(2)}"), ubic, fuente))
    return entradas


def _entrada(id_: str, tema: str, texto: str, ubicacion: str, fuente: dict) -> EntradaConocimiento:
    return EntradaConocimiento(id=id_, tipo="pasaje", tema=tema, texto=texto, documento=fuente["documento"],
                               ubicacion=ubicacion, url=fuente.get("url"), fecha_fuente=fuente.get("fecha_fuente"),
                               referencial=False, oficina=fuente.get("oficina"))


def pasajes_manuales(fuente: dict) -> list[EntradaConocimiento]:
    entradas = []
    for p in fuente.get("pasajes_manuales", []):
        sufijo = re.sub(r"[^0-9a-z]+", "-", p["ubicacion"].lower()).strip("-")
        entradas.append(_entrada(f"{fuente['id']}-{sufijo}", p["tema"], _compactar(p["texto"]), p["ubicacion"],
                                 fuente))
    return entradas


def validar(entradas: list[EntradaConocimiento]) -> list[str]:
    errores, ids = [], set()
    for e in entradas:
        if e.id in ids:
            errores.append(f"id duplicado: {e.id}")
        ids.add(e.id)
        if e.tema not in TEMAS:
            errores.append(f"{e.id}: tema desconocido {e.tema}")
        n = _palabras(e.texto)
        if not MIN_PALABRAS_PASAJE <= n <= MAX_PALABRAS_PASAJE:
            errores.append(f"{e.id}: {n} palabras (debe estar entre 20 y 400)")
        if not (e.documento and e.ubicacion and e.fecha_fuente):
            errores.append(f"{e.id}: falta documento, ubicación o fecha")
    return errores


def construir(config: Config | None = None) -> list[EntradaConocimiento]:
    config = config or Config()
    fuentes = yaml.safe_load(config.ruta("fuentes.yaml").read_text(encoding="utf-8"))
    entradas: list[EntradaConocimiento] = []
    for fuente in fuentes:
        entradas += pasajes_manuales(fuente)
        pdf = descargar(fuente, config)
        if pdf is not None:
            entradas += dividir_articulos(extraer_texto(pdf), fuente)
    errores = validar(entradas)
    if errores:
        raise ValueError("Pasajes inválidos:\n" + "\n".join(errores))
    guardar(entradas, config.ruta("conocimiento", "pasajes.jsonl"))
    return entradas


def guardar(entradas: list[EntradaConocimiento], ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8") as f:
        for e in entradas:
            f.write(json.dumps(asdict(e), ensure_ascii=False, default=str) + "\n")


def cargar_jsonl(ruta: Path) -> list[EntradaConocimiento]:
    if not ruta.exists():
        return []
    return [EntradaConocimiento(**json.loads(linea)) for linea in ruta.read_text(encoding="utf-8").splitlines()
            if linea.strip()]


if __name__ == "__main__":
    pasajes = construir()
    por_tema: dict[str, int] = {}
    for p in pasajes:
        por_tema[p.tema] = por_tema.get(p.tema, 0) + 1
    print(f"{len(pasajes)} pasajes → data/conocimiento/pasajes.jsonl")
    for tema, n in sorted(por_tema.items()):
        print(f"  {tema:<16} {n}")
