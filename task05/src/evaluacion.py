"""Evaluación de extremo a extremo de la recuperación con el filtro de intención (SC-003)."""

from __future__ import annotations

from src import politica
from src.preprocesamiento import procesar


def recuperacion_con_intencion(orq, ruta, simular_confirmacion: bool = True) -> dict:
    """Reproduce lo que hace el chatbot con cada pregunta: clasifica la intención, aplica la banda de
    confianza y, si corresponde, pide la respuesta directa al índice filtrada por tema (FR-019)."""
    cfg = orq.config
    filas = orq.indice.leer_preguntas(ruta)
    aciertos = n_con = correctas_sin = n_sin = 0
    detalle = []
    for fila in filas:
        r = orq.modelo.predecir(procesar(fila["pregunta"]))
        banda = politica.banda(r.confianza, cfg.UMBRAL_ACEPTAR, cfg.UMBRAL_RECHAZAR)
        if banda == "aceptar" and r.intencion == "fuera_de_dominio":
            respuesta = None  # el chatbot rechaza con el mensaje de alcance
        elif banda == "confirmar":
            # El chatbot pregunta «¿es sobre X o Y?». Con la simulación, el estudiante elige su tema real si
            # está entre los dos ofrecidos (un turno más); si no está, o sin simulación, no hay respuesta.
            ofrecidos = politica.opciones_confirmacion(r)
            elegido = fila["tema"] if simular_confirmacion and fila["tema"] in ofrecidos else None
            respuesta = orq.indice.respuesta_directa(fila["pregunta"], elegido) if elegido else None
        else:
            tema = r.intencion if banda == "aceptar" else None
            respuesta = orq.indice.respuesta_directa(fila["pregunta"], tema)
        obtenido = respuesta.fuentes[0].id if respuesta else ""
        esperado = fila["id_esperado"].strip()
        if esperado:
            n_con += 1
            aciertos += obtenido == esperado
        else:
            n_sin += 1
            correctas_sin += obtenido == ""
        detalle.append({"pregunta": fila["pregunta"], "intencion": r.intencion, "banda": banda,
                        "esperado": esperado, "obtenido": obtenido})
    return {"hit_at_1": aciertos / max(n_con, 1), "no_respuesta_correcta": correctas_sin / max(n_sin, 1),
            "n_con_respuesta": n_con, "n_sin_respuesta": n_sin, "detalle": detalle}


def guardar(orq=None) -> dict:
    """Mide la recuperación con intención (con y sin el turno de confirmación) y la guarda en reporte.json."""
    import json

    from src.config import REPORTE_EVALUACION
    from src.orquestador import Orquestador

    orq = orq or Orquestador.cargar()
    ruta = orq.config.ruta("evaluacion", "preguntas_retrieval.csv")
    resultado = {}
    for nombre, simular in (("prueba_pipeline", True), ("prueba_pipeline_sin_confirmacion", False)):
        m = recuperacion_con_intencion(orq, ruta, simular)
        resultado[nombre] = {k: v for k, v in m.items() if k != "detalle"}
    reporte = json.loads(REPORTE_EVALUACION.read_text(encoding="utf-8")) if REPORTE_EVALUACION.exists() else {}
    reporte.setdefault("retrieval", {}).update(resultado)
    REPORTE_EVALUACION.write_text(json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8")
    return resultado


if __name__ == "__main__":
    for nombre, m in guardar().items():
        print(f"{nombre:<34} acierto@1={m['hit_at_1']:.3f}  no-respuesta={m['no_respuesta_correcta']:.3f}")
