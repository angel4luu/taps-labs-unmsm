"""Componente 2 — NLP/ML: clasificación de intenciones.

Rama A (léxica): TF-IDF de raíces + n-gramas de caracteres, con tres clasificadores comparados
(Naive Bayes, Regresión Logística, SVM lineal calibrada). Rama B (semántica): embeddings
multilingües + Regresión Logística. La combinación A+B promedia probabilidades. La selección usa
validación cruzada estratificada de 5 folds y una regla fijada de antemano; el conjunto de prueba
(20 %) solo se usa una vez, al final.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass

import joblib
import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin, TransformerMixin, clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import GridSearchCV, StratifiedKFold, cross_val_predict, cross_validate
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

from src import embeddings, preprocesamiento
from src.config import DIR_EVALUACION, DIR_MODELOS, REPORTE_EVALUACION, Config
from src.modelos import Mensaje, ResultadoIntencion

ARCHIVO_MODELO = DIR_MODELOS / "intenciones.joblib"
COMPLEJIDAD = {"A·NB": 1, "A·LR": 2, "A·SVM": 3, "B·Emb+LR": 4, "A+B promedio": 5}


# --- datos -----------------------------------------------------------------------------------------
def cargar_ejemplos(config: Config | None = None) -> dict[str, list[str]]:
    config = config or Config()
    with config.ruta("intenciones", "ejemplos.csv").open(encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    datos = {"X_train": [], "y_train": [], "X_test": [], "y_test": []}
    for fila in filas:
        sufijo = "train" if fila["particion"] == "train" else "test"
        datos[f"X_{sufijo}"].append(fila["texto"])
        datos[f"y_{sufijo}"].append(fila["intencion"])
    return datos


# --- rama A: características léxicas ------------------------------------------------------------------
def caracteristicas_lexicas() -> FeatureUnion:
    return FeatureUnion([
        ("palabras", TfidfVectorizer(tokenizer=preprocesamiento.raices, preprocessor=None, lowercase=False,
                                     token_pattern=None, ngram_range=(1, 2), sublinear_tf=True)),
        ("caracteres", TfidfVectorizer(preprocessor=preprocesamiento.normalizar, analyzer="char_wb",
                                       ngram_range=(3, 5), sublinear_tf=True, min_df=2)),
    ])


def candidatos_a(semilla: int) -> dict[str, GridSearchCV]:
    interno = StratifiedKFold(3, shuffle=True, random_state=semilla)

    def grid(clf, params):
        return GridSearchCV(Pipeline([("tfidf", caracteristicas_lexicas()), ("clf", clf)]), params,
                            cv=interno, scoring="f1_macro", n_jobs=1)

    return {
        "A·NB": grid(MultinomialNB(), {"clf__alpha": [0.05, 0.2, 0.5]}),
        "A·LR": grid(LogisticRegression(max_iter=2000, class_weight="balanced"), {"clf__C": [3, 10, 30]}),
        "A·SVM": grid(CalibratedClassifierCV(LinearSVC(), cv=3), {"clf__estimator__C": [0.3, 1, 3]}),
    }


# --- rama B: embeddings -------------------------------------------------------------------------------
class Embeddings(BaseEstimator, TransformerMixin):
    """Convierte cada frase en su vector de 768 dimensiones (modelo multilingüe preentrenado)."""

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return embeddings.codificar(list(X))


def candidato_b(semilla: int) -> GridSearchCV:
    interno = StratifiedKFold(3, shuffle=True, random_state=semilla)
    pipe = Pipeline([("emb", Embeddings()), ("clf", LogisticRegression(max_iter=2000, class_weight="balanced"))])
    return GridSearchCV(pipe, {"clf__C": [1, 10, 30]}, cv=interno, scoring="f1_macro", n_jobs=1)


class PromedioAB(BaseEstimator, ClassifierMixin):
    """Combinación A+B: promedio de las probabilidades de la mejor rama A y de la rama B."""

    def __init__(self, modelo_a=None, modelo_b=None):
        self.modelo_a = modelo_a
        self.modelo_b = modelo_b

    def fit(self, X, y):
        self.a_ = clone(self.modelo_a).fit(X, y)
        self.b_ = clone(self.modelo_b).fit(X, y)
        self.classes_ = self.a_.classes_
        assert list(self.classes_) == list(self.b_.classes_)
        return self

    def predict_proba(self, X):
        return (self.a_.predict_proba(X) + self.b_.predict_proba(X)) / 2

    def predict(self, X):
        return self.classes_[np.argmax(self.predict_proba(X), axis=1)]


# --- regla de selección (fijada antes de ver los resultados) -------------------------------------------
def aplicar_regla(cv: list[dict]) -> tuple[str, str]:
    """1) Mayor media de F1 macro entre los modelos individuales. 2) Si la diferencia con otros es menor
    que una desviación estándar, es empate y se elige el más simple. 3) La combinación A+B solo se usa
    si supera al mejor individual por más de una desviación estándar."""
    individuales = [c for c in cv if c["candidato"] != "A+B promedio"]
    mejor = max(individuales, key=lambda c: c["f1_macro_media"])
    empatados = [c for c in individuales if mejor["f1_macro_media"] - c["f1_macro_media"] < mejor["f1_macro_std"]]
    simple = min(empatados, key=lambda c: c.get("complejidad", COMPLEJIDAD.get(c["candidato"], 9)))
    regla = (f"Mejor individual: {mejor['candidato']} ({mejor['f1_macro_media']:.3f} ± {mejor['f1_macro_std']:.3f}). "
             f"Empatados (diferencia < 1 std): {', '.join(c['candidato'] for c in empatados)} → el más simple es "
             f"{simple['candidato']}.")
    combinacion = next((c for c in cv if c["candidato"] == "A+B promedio"), None)
    if combinacion and combinacion["f1_macro_media"] > mejor["f1_macro_media"] + mejor["f1_macro_std"]:
        return "A+B promedio", regla + (f" La combinación ({combinacion['f1_macro_media']:.3f}) supera al mejor "
                                        f"individual por más de una std → se usa A+B.")
    if combinacion:
        regla += (f" La combinación ({combinacion['f1_macro_media']:.3f}) no supera al mejor individual por más de "
                  f"una std → no se usa.")
    return simple["candidato"], regla


# --- umbrales de confianza --------------------------------------------------------------------------
def ajustar_umbrales(confianzas: np.ndarray, correctas: np.ndarray) -> dict:
    """Aceptar: el menor umbral con precisión ≥ 0.90 entre lo aceptado (en [0.50, 0.75]).
    Rechazar: el mayor umbral con exactitud < 0.5 por debajo de él (en [0.25, 0.45])."""
    aceptar = 0.75
    for t in np.arange(0.50, 0.751, 0.01):
        sel = confianzas >= t
        if sel.any() and correctas[sel].mean() >= 0.90:
            aceptar = float(round(t, 2))
            break
    rechazar = 0.25
    for t in np.arange(0.45, 0.249, -0.01):
        sel = confianzas < t
        if sel.sum() >= 3 and correctas[sel].mean() < 0.5:
            rechazar = float(round(t, 2))
            break
    return {"aceptar": aceptar, "rechazar": min(rechazar, aceptar - 0.1),
            "metodo": "probabilidades fuera de fold (validación cruzada) del modelo seleccionado"}


# --- modelo para el chatbot -------------------------------------------------------------------------
@dataclass
class ModeloIntenciones:
    estimador: object
    nombre: str

    def probabilidades(self, texto: str) -> list[tuple[str, float]]:
        proba = self.estimador.predict_proba([texto])[0]
        orden = np.argsort(-proba)
        return [(str(self.estimador.classes_[i]), float(proba[i])) for i in orden]

    def predecir(self, mensaje: Mensaje) -> ResultadoIntencion:
        ranking = self.probabilidades(mensaje.texto_original)
        intencion, confianza = ranking[0]
        return ResultadoIntencion(intencion=intencion, confianza=confianza, top2=ranking[:3], modelo=self.nombre,
                                  banda="")


def palabras_clave(estimador_lr, clases, n: int = 10) -> dict[str, list[str]]:
    """Raíces con mayor peso por intención en la Regresión Logística (interpretabilidad)."""
    pipe = estimador_lr.best_estimator_ if hasattr(estimador_lr, "best_estimator_") else estimador_lr
    palabras = pipe.named_steps["tfidf"].transformer_list[0][1]
    nombres = np.array(palabras.get_feature_names_out())
    coef = pipe.named_steps["clf"].coef_[:, : len(nombres)]
    return {str(c): nombres[np.argsort(-coef[i])[:n]].tolist() for i, c in enumerate(clases)}


# --- entrenamiento, selección y reporte --------------------------------------------------------------
def entrenar_y_seleccionar(datos: dict | None = None, semilla: int = 42, guardar: bool = True,
                           verbose: bool = False):
    datos = datos or cargar_ejemplos()
    X, y = np.array(datos["X_train"], dtype=object), np.array(datos["y_train"])
    Xt, yt = np.array(datos["X_test"], dtype=object), np.array(datos["y_test"])
    externo = StratifiedKFold(5, shuffle=True, random_state=semilla)

    candidatos = {**candidatos_a(semilla), "B·Emb+LR": candidato_b(semilla)}
    cv = []
    for nombre, modelo in candidatos.items():
        r = cross_validate(modelo, X, y, cv=externo, scoring="f1_macro")
        cv.append({"candidato": nombre, "f1_macro_media": float(r["test_score"].mean()),
                   "f1_macro_std": float(r["test_score"].std()), "por_fold": r["test_score"].round(4).tolist(),
                   "complejidad": COMPLEJIDAD[nombre]})
        if verbose:
            print(f"  {nombre:<14} {cv[-1]['f1_macro_media']:.3f} ± {cv[-1]['f1_macro_std']:.3f}")
    mejor_a = max((c for c in cv if c["candidato"].startswith("A·")), key=lambda c: c["f1_macro_media"])
    combinacion = PromedioAB(candidatos[mejor_a["candidato"]], candidatos["B·Emb+LR"])
    r = cross_validate(combinacion, X, y, cv=externo, scoring="f1_macro")
    cv.append({"candidato": "A+B promedio", "f1_macro_media": float(r["test_score"].mean()),
               "f1_macro_std": float(r["test_score"].std()), "por_fold": r["test_score"].round(4).tolist(),
               "complejidad": COMPLEJIDAD["A+B promedio"], "rama_a": mejor_a["candidato"]})
    if verbose:
        print(f"  {'A+B promedio':<14} {cv[-1]['f1_macro_media']:.3f} ± {cv[-1]['f1_macro_std']:.3f}")

    ganador, regla = aplicar_regla(cv)
    estimador = combinacion if ganador == "A+B promedio" else candidatos[ganador]
    oof = cross_val_predict(clone(estimador), X, y, cv=externo, method="predict_proba")
    clases = np.unique(y)
    umbrales = ajustar_umbrales(oof.max(axis=1), clases[oof.argmax(axis=1)] == y)

    final = clone(estimador).fit(X, y)  # reentrenado con todo el conjunto de entrenamiento
    pred = final.predict(Xt)
    proba = final.predict_proba(Xt)
    errores = [{"texto": t, "real": r_, "predicho": p, "confianza": round(float(c), 3)}
               for t, r_, p, c in zip(Xt, yt, pred, proba.max(axis=1)) if r_ != p]
    lr = clone(candidatos["A·LR"]).fit(X, y)
    reporte = {
        "cv": cv,
        "seleccion": {"ganador": ganador, "regla_aplicada": regla,
                      "justificacion": "Regla fijada antes de ver los resultados (concept-decisions.md)."},
        "test": {"accuracy": float(accuracy_score(yt, pred)), "f1_macro": float(f1_score(yt, pred, average="macro")),
                 "n": int(len(yt)), "reporte_por_intencion": classification_report(yt, pred, output_dict=True,
                                                                                    zero_division=0),
                 "clases": clases.tolist(), "matriz_confusion": confusion_matrix(yt, pred, labels=clases).tolist()},
        "errores": errores,
        "umbrales": umbrales,
        "palabras_clave": palabras_clave(lr, lr.classes_),
    }
    modelo = ModeloIntenciones(final, ganador)
    if guardar:
        guardar_reporte(reporte)
        DIR_MODELOS.mkdir(parents=True, exist_ok=True)
        joblib.dump(modelo, ARCHIVO_MODELO)
        graficos(reporte)
    return reporte, modelo


def guardar_reporte(reporte: dict) -> None:
    previo = json.loads(REPORTE_EVALUACION.read_text(encoding="utf-8")) if REPORTE_EVALUACION.exists() else {}
    umbrales = {**previo.get("umbrales", {}), **{k: v for k, v in reporte["umbrales"].items()}}
    REPORTE_EVALUACION.parent.mkdir(parents=True, exist_ok=True)
    REPORTE_EVALUACION.write_text(json.dumps({**previo, **reporte, "umbrales": umbrales}, ensure_ascii=False,
                                             indent=2), encoding="utf-8")


def graficos(reporte: dict) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    DIR_EVALUACION.mkdir(parents=True, exist_ok=True)
    cv = reporte["cv"]
    ganador = reporte["seleccion"]["ganador"]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    nombres = [c["candidato"] for c in cv]
    colores = ["#1f6feb" if n == ganador else "#9aa4b2" for n in nombres]
    ax.barh(nombres, [c["f1_macro_media"] for c in cv], xerr=[c["f1_macro_std"] for c in cv], color=colores,
            capsize=4)
    ax.set_xlim(0.5, 1.0)
    ax.invert_yaxis()
    ax.set_xlabel("F1 macro (media ± desv. estándar, 5 folds)")
    ax.set_title(f"Comparación de candidatos — seleccionado: {ganador}")
    for i, c in enumerate(cv):
        ax.text(c["f1_macro_media"] + c["f1_macro_std"] + 0.005, i, f"{c['f1_macro_media']:.3f}", va="center")
    fig.tight_layout()
    fig.savefig(DIR_EVALUACION / "comparacion_cv.png", dpi=150)
    plt.close(fig)

    clases = reporte["test"]["clases"]
    matriz = np.array(reporte["test"]["matriz_confusion"])
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.imshow(matriz, cmap="Blues")
    ax.set_xticks(range(len(clases)), clases, rotation=45, ha="right")
    ax.set_yticks(range(len(clases)), clases)
    for i in range(len(clases)):
        for j in range(len(clases)):
            if matriz[i, j]:
                ax.text(j, i, matriz[i, j], ha="center", va="center",
                        color="white" if matriz[i, j] > matriz.max() / 2 else "black")
    ax.set_xlabel("Predicho")
    ax.set_ylabel("Real")
    ax.set_title(f"Matriz de confusión (prueba, n={reporte['test']['n']}) — "
                 f"accuracy {reporte['test']['accuracy']:.2f}")
    fig.tight_layout()
    fig.savefig(DIR_EVALUACION / "matriz_confusion.png", dpi=150)
    plt.close(fig)


def cargar_modelo(config: Config | None = None) -> ModeloIntenciones:
    if ARCHIVO_MODELO.exists():
        return joblib.load(ARCHIVO_MODELO)
    return entrenar_y_seleccionar(cargar_ejemplos(config))[1]


def main() -> None:
    print("Validación cruzada (5 folds, F1 macro):")
    rep, _ = entrenar_y_seleccionar(verbose=True)
    print("\n" + rep["seleccion"]["regla_aplicada"])
    print(f"\nPrueba (n={rep['test']['n']}): accuracy={rep['test']['accuracy']:.3f}  "
          f"F1 macro={rep['test']['f1_macro']:.3f}")
    print(f"Umbrales: aceptar={rep['umbrales']['aceptar']}  rechazar={rep['umbrales']['rechazar']}")
    print(f"Errores en prueba: {len(rep['errores'])}")
    for e in rep["errores"]:
        print(f"  «{e['texto']}» real={e['real']} predicho={e['predicho']} ({e['confianza']})")


if __name__ == "__main__":
    # Se importa el módulo por su nombre para que el modelo guardado refiera a src.intenciones
    # (y no a __main__) y pueda cargarse desde el notebook o los tests.
    from src import intenciones

    intenciones.main()
