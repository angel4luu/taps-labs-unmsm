"""Conversaciones de demostración (4 casos de uso + escenas por componente): ejecutar, verificar y exportar."""

from __future__ import annotations

from pathlib import Path

import yaml

from src.config import DIR_FLUJOS, Config
from src.interfaz import render_html
from src.modelos import Componente, Mensaje, Politica, Respuesta

FAMILIA_LLM = {Componente.LLM, Componente.LLM_LOCAL, Componente.FALLBACK_EXTRACTIVO}
FAMILIA_FALLBACK = {Componente.LLM_LOCAL, Componente.FALLBACK_EXTRACTIVO}


def cargar(config: Config | None = None, tipo: str | None = None) -> list[dict]:
    """Casos de uso y escenas; cada uno lleva `tipo` = "caso" | "escena". `tipo` filtra."""
    config = config or Config()
    datos = yaml.safe_load(config.ruta("flujos.yaml").read_text(encoding="utf-8"))
    todos = [{**c, "tipo": "caso"} for c in datos.get("casos", [])] + \
            [{**e, "tipo": "escena"} for e in datos.get("escenas", [])]
    return [f for f in todos if tipo is None or f["tipo"] == tipo]


def flujo(id_, config: Config | None = None) -> dict:
    return next(f for f in cargar(config) if str(f["id"]) == str(id_))


def nombre_archivo(datos: dict) -> str:
    return f"{datos['tipo']}_{datos['id']}"


def titulo(datos: dict) -> str:
    return f"Caso {datos['id']} — {datos['titulo']}" if datos["tipo"] == "caso" else datos["titulo"]


def ejecutar(id_: int, orq) -> list[tuple[Mensaje, Respuesta]]:
    """Corre el flujo en una sesión nueva; solo el flujo con `forzar_offline` usa el modo sin conexión."""
    datos = flujo(id_, orq.config)
    sesion = orq.nueva_sesion()
    anterior = orq.forzar_offline
    orq.forzar_offline = bool(datos.get("forzar_offline"))
    try:
        for turno in datos["turnos"]:
            orq.responder(turno["usuario"], sesion)
    finally:
        orq.forzar_offline = anterior
    return list(sesion.historial)


def _componente_ok(esperado: str, obtenido: Componente, en_linea: bool) -> bool:
    if esperado == "FALLBACK":
        return obtenido in FAMILIA_FALLBACK
    if esperado == "LLM":
        return obtenido == Componente.LLM if en_linea else obtenido in FAMILIA_LLM
    return obtenido == Componente[esperado]


def verificar(id_: int, turnos, config: Config | None = None, en_linea: bool | None = None) -> list[str]:
    """Diferencias entre lo obtenido y `esperado` en flujos.yaml (lista vacía = el flujo se comporta bien)."""
    from src.config import hay_credencial_online

    config = config or Config()
    if en_linea is None:
        en_linea = config.LLM_MODO != "offline" and hay_credencial_online()
    datos = flujo(id_, config)
    errores = []
    for k, (turno, (_, r)) in enumerate(zip(datos["turnos"], turnos), start=1):
        esp = turno["esperado"]
        if not _componente_ok(esp["componente"], r.componente, en_linea):
            errores.append(f"flujo {id_} turno {k}: componente {r.componente.name}, se esperaba {esp['componente']}")
        faltan = [p for p in esp.get("politica", []) if Politica[p] not in r.politica]
        if faltan:
            errores.append(f"flujo {id_} turno {k}: faltan políticas {faltan} (obtenidas {[p.name for p in r.politica]})")
        if "intencion" in esp and (r.intencion is None or r.intencion.intencion != esp["intencion"]):
            obtenida = r.intencion.intencion if r.intencion else None
            errores.append(f"flujo {id_} turno {k}: intención {obtenida}, se esperaba {esp['intencion']}")
        for tipo, valor in (esp.get("detalles") or {}).items():
            if not any(d.tipo == tipo and d.valor == str(valor) for d in r.detalles):
                errores.append(f"flujo {id_} turno {k}: falta el detalle {tipo}={valor}")
    if len(turnos) != len(datos["turnos"]):
        errores.append(f"flujo {id_}: {len(turnos)} turnos, se esperaban {len(datos['turnos'])}")
    return errores


def senal_clave(r: Respuesta) -> str:
    """Columna «Señal clave» de la tabla de las diapositivas, generada desde la respuesta."""
    partes = []
    if r.regla:
        partes.append(f"regla {r.regla}")
    elif r.intencion:
        partes.append(f"{r.intencion.intencion} · {r.intencion.confianza:.2f}")
    detalles = [d.etiqueta() for d in r.detalles if d.tipo in {"facultad", "curso", "veces", "periodo"}]
    if detalles:
        partes.append(", ".join(detalles))
    if r.fuentes:
        f = r.fuentes[0]
        partes.append(f"{f.ubicacion}" + (f" ({f.score:.2f})" if f.score is not None else ""))
    return "; ".join(partes)


def traza(turnos) -> list[dict]:
    return [{"Turno": k, "Usuario": m.texto_original, "Componente": r.componente.value,
             "Política": ", ".join(p.value for p in r.politica) or "—", "Señal clave": senal_clave(r)}
            for k, (m, r) in enumerate(turnos, start=1)]


def exportar_html(id_, turnos, config: Config | None = None, destino: Path = DIR_FLUJOS) -> Path:
    datos = flujo(id_, config)
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / f"{nombre_archivo(datos)}.html"
    cuerpo = render_html(turnos, titulo(datos), numerar=True)
    ruta.write_text(f'<!doctype html><html lang="es"><head><meta charset="utf-8"><title>{titulo(datos)}</title></head>'
                    f'<body style="margin:0;padding:16px;background:#ffffff">{cuerpo}</body></html>',
                    encoding="utf-8")
    return ruta


def ejecutar_todos(orq, tipo: str | None = "caso") -> dict:
    """Por defecto los 4 casos de uso; tipo=None corre también las escenas."""
    return {f["id"]: ejecutar(f["id"], orq) for f in cargar(orq.config, tipo)}


if __name__ == "__main__":
    import json
    import sys

    from src.config import DIR_EVIDENCIA
    from src.orquestador import Orquestador

    orq = Orquestador.cargar()
    resultados = ejecutar_todos(orq, tipo=None)
    for viejo in (DIR_EVIDENCIA / "flujos").glob("*.html"):
        viejo.unlink()
    errores, trazas = [], {}
    for id_, turnos in resultados.items():
        exportar_html(id_, turnos, orq.config)
        errores += verificar(id_, turnos, orq.config)
        trazas[str(id_)] = traza(turnos)
        for fila in trazas[str(id_)]:
            print(f"  {str(id_):<12}T{fila['Turno']} [{fila['Componente']:<20}] {fila['Política']:<28} {fila['Señal clave'][:60]}")
    (DIR_EVIDENCIA / "flujos" / "trazas.json").write_text(json.dumps(trazas, ensure_ascii=False, indent=2),
                                                         encoding="utf-8")
    if "--capturas" in sys.argv:
        from src import capturas

        for vieja in (DIR_EVIDENCIA / "capturas").glob("*_*.png"):
            if not vieja.name.startswith("widget"):
                vieja.unlink()
        capturas.capturar(sorted((DIR_EVIDENCIA / "flujos").glob("*.html")))
    print("\n" + (f"✅ {len(resultados)} conversaciones sin diferencias" if not errores else "\n".join(errores)))
    sys.exit(1 if errores else 0)
