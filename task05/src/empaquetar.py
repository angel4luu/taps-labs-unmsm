"""Paquete del proyecto (G1_task05_codigo.zip): lo necesario para ejecutar el notebook en otra computadora."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from src.config import DIR_ENTREGABLES, RAIZ

NOMBRE_ZIP = "G1_task05_codigo.zip"
NOTEBOOK = "G1_task05_chatbot_hibrido.ipynb"
# Incluye el modelo de intención entrenado (modelos/) y el PDF del reglamento (data/raw/) para no depender
# de reentrenar ni de descargar el reglamento.
INCLUIR = ["src", "data", "modelos", "tests", "evidencia", "environment.yml", "requirements.txt", "README.md",
           ".env.example"]
EXCLUIR = re.compile(r"(^|/)(\.env$|__pycache__|\.ipynb_checkpoints|\.pytest_cache)")
CLAVE = re.compile(rb"AIza[0-9A-Za-z_\-]{20,}")


def _archivos() -> list[Path]:
    archivos = []
    for nombre in INCLUIR:
        ruta = RAIZ / nombre
        if not ruta.exists():
            continue
        candidatos = [ruta] if ruta.is_file() else sorted(p for p in ruta.rglob("*") if p.is_file())
        archivos += [p for p in candidatos if not EXCLUIR.search(p.relative_to(RAIZ).as_posix())]
    return archivos


def codigo() -> Path:
    destino = DIR_ENTREGABLES / NOMBRE_ZIP
    destino.parent.mkdir(parents=True, exist_ok=True)
    # El notebook va ya ejecutado (con salidas) en la raíz del proyecto
    notebook = DIR_ENTREGABLES / NOTEBOOK if (DIR_ENTREGABLES / NOTEBOOK).exists() else RAIZ / NOTEBOOK
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zf:
        for archivo in _archivos():
            zf.write(archivo, f"task05/{archivo.relative_to(RAIZ).as_posix()}")
        zf.write(notebook, f"task05/{NOTEBOOK}")
    # Verificación: ningún .env ni nada con forma de clave de Gemini dentro del paquete (FR-025)
    with zipfile.ZipFile(destino) as zf:
        nombres = zf.namelist()
        assert not any(n.endswith("/.env") for n in nombres), "el paquete contiene un .env"
        for n in nombres:
            assert not CLAVE.search(zf.read(n)), f"{n} contiene algo con forma de clave"
    return destino


if __name__ == "__main__":
    ruta = codigo()
    with zipfile.ZipFile(ruta) as zf:
        print(f"✅ {ruta.relative_to(RAIZ)}: {len(zf.namelist())} archivos, {ruta.stat().st_size / 1024 ** 2:.1f} MB")
