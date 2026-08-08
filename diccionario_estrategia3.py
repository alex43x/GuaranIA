"""
diccionario_estrategia3.py
==============================
ÚNICA RESPONSABILIDAD: leer las oraciones base de raw/estrategia5/
(la MISMA base que usa run_strategy_3.py para reordenar — no lo que
ya reordenó, son dos transformaciones independientes sobre el mismo
origen) y generar hasta 3 variantes por sinónimo, usando el
diccionario del repo SyntaxGrammar-es-gn.

Regla de negocio: de UNA oración base salen como máximo 4 reordenadas
(run_strategy_3.py) Y, por separado, hasta 3 por sinónimo (este
archivo) — no una cadena de una transformación sobre la otra.

Requisitos: pip install google-genai pandas python-dotenv --break-system-packages
Necesita: .env con GEMINI_API_KEY, y el repo SyntaxGrammar-es-gn
          clonado como carpeta hermana.
"""

import os
import glob
import random
import json
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

CARPETA_BASE_ESTRATEGIA5 = os.path.join("raw", "estrategia5")
CARPETA_SALIDA = os.path.join("raw", "estrategia3_diccionario")

RUTA_REPO_GRAMATICA = "../SyntaxGrammar-es-gn"
RUTA_NOUNS = os.path.join(RUTA_REPO_GRAMATICA, "guarani/nouns/matched-nouns.csv")
RUTA_VERBS = os.path.join(RUTA_REPO_GRAMATICA, "guarani/verbs/matched-verbs-guarani.csv")

COLUMNAS_NOUNS = ["guarani", "espanol_forma", "espanol_lema", "pos", "subpos", "genero", "numero"]
COLUMNAS_VERBS = [
    "guarani_forma", "guarani_raiz", "pos1", "modo", "tiempo", "persona", "numero",
    "clusividad", "reg", "transitividad", "c1", "c2",
    "espanol_forma", "espanol_lema", "pos2", "subpos2", "modo2", "tiempo2",
    "persona2", "numero2", "c3", "transitividad2", "c4", "c5",
]


# ─────────────────────────────────────────────────────────────
# Leer las oraciones base de la Estrategia 5 (misma fuente que
# run_strategy_3.py, no lo que esa ya transformó)
# ─────────────────────────────────────────────────────────────
def leer_base_estrategia5() -> list[dict]:
    archivos = sorted(glob.glob(os.path.join(CARPETA_BASE_ESTRATEGIA5, "*.jsonl")))
    if not archivos:
        raise FileNotFoundError(
            f"No hay nada en {CARPETA_BASE_ESTRATEGIA5}/. Corré primero generar_estrategia_5()."
        )
    todas = []
    for archivo in archivos:
        df = pd.read_json(archivo, lines=True)
        print(f"  {os.path.basename(archivo)}: {len(df)} oraciones")
        todas.append(df)
    return pd.concat(todas, ignore_index=True).to_dict("records")


# ─────────────────────────────────────────────────────────────
# Diccionarios (sustantivos, verbos)
# ─────────────────────────────────────────────────────────────
def cargar_diccionarios():
    df_nouns = pd.read_csv(RUTA_NOUNS, header=None, names=COLUMNAS_NOUNS, encoding="utf-8")

    try:
        df_verbs = pd.read_csv(RUTA_VERBS, header=None, names=COLUMNAS_VERBS, encoding="utf-8")
    except pd.errors.ParserError:
        # Algunas filas (verbos compuestos tipo "hacer_referencia") tienen
        # un campo de más y rompen el parser rápido — se saltean esas
        # filas puntuales en vez de perder el archivo entero.
        print("  ⚠️  Filas malformadas detectadas en el CSV de verbos, saltando esas líneas...")
        df_verbs = pd.read_csv(
            RUTA_VERBS, header=None, names=COLUMNAS_VERBS, encoding="utf-8",
            engine="python", on_bad_lines="warn",
        )

    return df_nouns, df_verbs


def buscar_pos(palabra: str, df_nouns: pd.DataFrame, df_verbs: pd.DataFrame):
    en_nouns = df_nouns[df_nouns["guarani"] == palabra]
    if not en_nouns.empty:
        return "sustantivo", en_nouns.iloc[0]
    en_verbs = df_verbs[df_verbs["guarani_forma"] == palabra]
    if not en_verbs.empty:
        return "verbo", en_verbs.iloc[0]
    return None, None


def sinonimo_sustantivo(palabra: str, df_nouns: pd.DataFrame) -> str | None:
    fila = df_nouns[df_nouns["guarani"] == palabra]
    if fila.empty:
        return None
    lema = fila.iloc[0]["espanol_lema"]
    candidatos = df_nouns[(df_nouns["espanol_lema"] == lema) & (df_nouns["guarani"] != palabra)]
    if candidatos.empty:
        return None
    return candidatos.sample(1).iloc[0]["guarani"]


def conjugar_verbo(lema_es: str, modo, tiempo, persona, numero, df_verbs: pd.DataFrame) -> str | None:
    fila = df_verbs[
        (df_verbs["espanol_lema"] == lema_es)
        & (df_verbs["modo"] == modo)
        & (df_verbs["tiempo"] == tiempo)
        & (df_verbs["persona"] == persona)
        & (df_verbs["numero"] == numero)
    ]
    if fila.empty:
        return None
    return fila.sample(1).iloc[0]["guarani_forma"]


def pedir_sinonimo_verbo_es(lema_original: str, client) -> str:
    prompt = (
        f"Dame UN sinónimo en español, en infinitivo, del verbo '{lema_original}'. "
        f"Respondé solo el infinitivo, una palabra, sin explicación."
    )
    response = client.models.generate_content(model="gemini-3.5-flash", contents=prompt)
    return response.text.strip().lower()


def aplicar_diccionario(oracion: str, df_nouns: pd.DataFrame, df_verbs: pd.DataFrame,
                          client, max_reemplazos: int = 3) -> tuple[str | None, list[str]]:
    """
    Genera UNA oración con hasta max_reemplazos palabras cambiadas por
    sinónimo SIMULTÁNEAMENTE (no una oración por cada reemplazo).
    Nunca reemplaza más palabras de las que realmente tienen match en
    el diccionario — si solo hay 1 candidato real, reemplaza 1, no 3.

    Devuelve (oracion_nueva, metodos_usados) o (None, []) si no hubo
    ningún candidato real.
    """
    palabras = oracion.split()

    # 1. Encontrar TODOS los candidatos reales de la oración
    candidatos = []
    for idx, palabra in enumerate(palabras):
        palabra_limpia = palabra.strip(".,;:!?¡¿'\"")
        pos, fila = buscar_pos(palabra_limpia, df_nouns, df_verbs)
        if pos:
            candidatos.append((idx, pos, fila, palabra_limpia))

    if not candidatos:
        return None, []  # ningún candidato — no hay variante

    random.shuffle(candidatos)  # variar qué palabras se priorizan entre corridas

    # 2. Reemplazar hasta max_reemplazos, todos en la MISMA oración
    palabras_nuevas = palabras.copy()
    metodos_usados = []

    for idx, pos, fila, palabra_limpia in candidatos:
        if len(metodos_usados) >= max_reemplazos:
            break

        nuevo = None
        if pos == "sustantivo":
            nuevo = sinonimo_sustantivo(palabra_limpia, df_nouns)
            metodo = "sustantivo"
        else:  # verbo
            lema_nuevo = pedir_sinonimo_verbo_es(fila["espanol_lema"], client)
            nuevo = conjugar_verbo(lema_nuevo, fila["modo"], fila["tiempo"], fila["persona"], fila["numero"], df_verbs)
            metodo = "verbo"

        if nuevo:
            palabras_nuevas[idx] = nuevo
            metodos_usados.append(metodo)

    if not metodos_usados:
        return None, []  # había candidatos pero ninguno dio reemplazo válido

    return " ".join(palabras_nuevas), metodos_usados


# ─────────────────────────────────────────────────────────────
# Guardar (carpeta propia, no se mezcla con raw/estrategia3/)
# ─────────────────────────────────────────────────────────────
def guardar(registros: list[dict]) -> str:
    os.makedirs(CARPETA_SALIDA, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta = os.path.join(CARPETA_SALIDA, f"lote_{timestamp}.jsonl")
    with open(ruta, "w", encoding="utf-8") as f:
        for reg in registros:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")
    print(f"Guardado: {ruta} ({len(registros)} registros)")
    return ruta


# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        raise ValueError("Falta GEMINI_API_KEY o API_KEY en el .env")
    client = genai.Client(api_key=api_key)

    print("=== Leyendo raw/estrategia5/ (oraciones base) ===")
    oraciones = leer_base_estrategia5()
    print(f"Total: {len(oraciones)} oraciones base")

    print("\n=== Cargando diccionarios ===")
    df_nouns, df_verbs = cargar_diccionarios()
    print(f"Sustantivos: {len(df_nouns)} filas. Verbos: {len(df_verbs)} filas.")

    print("\n=== Aplicando diccionario (hasta 3 palabras con sinónimo, en la MISMA oración) ===")
    registros = []
    sin_candidatos = 0
    for item in oraciones:
        texto_nuevo, metodos = aplicar_diccionario(item["texto"], df_nouns, df_verbs, client, max_reemplazos=3)
        if texto_nuevo is None:
            sin_candidatos += 1
            continue
        registros.append({
            "texto": texto_nuevo,
            "texto_base": item["texto"],
            "tipo_transformacion": f"diccionario_{len(metodos)}reemplazos",
            "detalle_reemplazos": metodos,  # ej. ["sustantivo", "verbo"] — qué tipo se cambió, en orden
            "dominio": item.get("dominio", "sin_clasificar"),
            "estrategia": "3",
        })

    print(f"\n{len(registros)} oraciones con al menos 1 reemplazo "
          f"({sin_candidatos} sin ningún candidato en el diccionario).")
    guardar(registros)