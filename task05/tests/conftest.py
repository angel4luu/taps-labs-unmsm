import shutil
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.config import Config  # noqa: E402
from src.modelos import Componente, Fuente, Politica, Respuesta, Sesion  # noqa: E402


@pytest.fixture
def config(tmp_path):
    """Config con una copia de data/ (sin raw/) para que los tests no modifiquen los datos reales."""
    destino = tmp_path / "data"
    shutil.copytree(RAIZ / "data", destino, ignore=shutil.ignore_patterns("raw"))
    return Config(dir_data=destino, LLM_MODO="offline")


@pytest.fixture
def sesion():
    return Sesion()


@pytest.fixture
def stub_llm(monkeypatch):
    """Sustituye el LLM por una respuesta determinista que cita el primer pasaje."""
    from src import llm

    llamadas = []

    def responder(pregunta, pasajes, intencion=None, detalles=None, historial=None, forzar_offline=False,
                  config=None):
        llamadas.append(pregunta)
        fuentes = [Fuente(id=p.id, documento=p.documento, ubicacion=p.ubicacion) for p in pasajes[:1]]
        if forzar_offline:
            return Respuesta(texto=f"[stub local] {pregunta}", componente=Componente.LLM_LOCAL, fuentes=fuentes,
                             politica=[Politica.FALLBACK_OFFLINE])
        return Respuesta(texto=f"[stub] {pregunta}", componente=Componente.LLM, fuentes=fuentes)

    monkeypatch.setattr(llm, "responder", responder)
    return llamadas
