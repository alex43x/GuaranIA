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
RUTA_ADJ = os.path.join(RUTA_REPO_GRAMATICA, "guarani/adjectives/matched-adjectives-guarani.csv")

COLUMNAS_NOUNS = ["guarani", "espanol_forma", "espanol_lema", "pos", "subpos", "genero", "numero"]
COLUMNAS_VERBS = [
    "guarani_forma", "guarani_raiz", "pos1", "modo", "tiempo", "persona", "numero",
    "clusividad", "reg", "transitividad", "c1", "c2",
    "espanol_forma", "espanol_lema", "pos2", "subpos2", "modo2", "tiempo2",
    "persona2", "numero2", "c3", "transitividad2", "c4", "c5",
]
COLUMNAS_ADJ = [
    "guarani", "guarani_forma2", "pos", "subpos", "espanol_forma", "espanol_lema",
    "pos2", "subpos2", "c1", "genero", "numero", "c2", "c3",
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
    df_adj = pd.read_csv(RUTA_ADJ, header=None, names=COLUMNAS_ADJ, encoding="utf-8")

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

    return df_nouns, df_verbs, df_adj


def calcular_palabras_ambiguas(df_nouns: pd.DataFrame, df_verbs: pd.DataFrame, df_adj: pd.DataFrame) -> set:
    """
    Palabras guaraní que aparecen en MÁS DE UNA tabla (sustantivo Y
    adjetivo, sustantivo Y verbo, etc.) — resuelve ambigüedades tipo
    'guasu' (venado / aumentativo 'grande') sin gastar ni un llamado
    a la IA: si es ambigua, directamente no se toca.
    """
    nouns_set = set(df_nouns["guarani"])
    verbs_set = set(df_verbs["guarani_forma"])
    adj_set = set(df_adj["guarani"])
    return (nouns_set & verbs_set) | (nouns_set & adj_set) | (verbs_set & adj_set)


def buscar_pos(palabra: str, df_nouns: pd.DataFrame, df_verbs: pd.DataFrame, df_adj: pd.DataFrame,
                palabras_ambiguas: set):
    if palabra in palabras_ambiguas:
        return None, None  # ambigua entre tablas — no se toca, sin gastar API para decidir

    en_nouns = df_nouns[df_nouns["guarani"] == palabra]
    if not en_nouns.empty:
        return "sustantivo", en_nouns.iloc[0]
    en_verbs = df_verbs[df_verbs["guarani_forma"] == palabra]
    if not en_verbs.empty:
        return "verbo", en_verbs.iloc[0]
    en_adj = df_adj[df_adj["guarani"] == palabra]
    if not en_adj.empty:
        return "adjetivo", en_adj.iloc[0]
    return None, None


def _normalizar_para_comparar(texto: str) -> str:
    import re
    t = texto.lower().strip()
    t = re.sub(r"[.,;:!?¡¿'\"]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t


def sinonimo_sustantivo(palabra: str, df_nouns: pd.DataFrame, excluir: set | None = None) -> str | None:
    excluir = excluir or set()
    fila = df_nouns[df_nouns["guarani"] == palabra]
    if fila.empty:
        return None
    lema = fila.iloc[0]["espanol_lema"]
    candidatos = df_nouns[
        (df_nouns["espanol_lema"] == lema) & (~df_nouns["guarani"].isin({palabra} | excluir))
    ]
    if candidatos.empty:
        return None
    return candidatos.sample(1).iloc[0]["guarani"]


def contar_alternativas_sustantivo(palabra: str, df_nouns: pd.DataFrame) -> int:
    """Cuántos sinónimos distintos existen realmente para esta palabra — usado para priorizar."""
    fila = df_nouns[df_nouns["guarani"] == palabra]
    if fila.empty:
        return 0
    lema = fila.iloc[0]["espanol_lema"]
    return df_nouns[(df_nouns["espanol_lema"] == lema) & (df_nouns["guarani"] != palabra)]["guarani"].nunique()


def sinonimo_adjetivo(palabra: str, df_adj: pd.DataFrame, excluir: set | None = None) -> str | None:
    """
    El guaraní de esta tabla es invariable en género/número (una sola
    forma cubre las 4 combinaciones del español) — no hace falta
    concordancia al elegir el reemplazo, a diferencia de sustantivos.
    """
    excluir = excluir or set()
    fila = df_adj[df_adj["guarani"] == palabra]
    if fila.empty:
        return None
    lema = fila.iloc[0]["espanol_lema"]
    candidatos = df_adj[
        (df_adj["espanol_lema"] == lema) & (~df_adj["guarani"].isin({palabra} | excluir))
    ]
    if candidatos.empty:
        return None
    return candidatos.sample(1).iloc[0]["guarani"]


def contar_alternativas_adjetivo(palabra: str, df_adj: pd.DataFrame) -> int:
    fila = df_adj[df_adj["guarani"] == palabra]
    if fila.empty:
        return 0
    lema = fila.iloc[0]["espanol_lema"]
    return df_adj[(df_adj["espanol_lema"] == lema) & (df_adj["guarani"] != palabra)]["guarani"].nunique()


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


import re


def _separar_puntuacion(palabra: str) -> tuple[str, str, str]:
    """Separa una palabra en (prefijo de puntuación, núcleo, sufijo de puntuación),
    para poder buscar/reemplazar el núcleo sin perder la puntuación pegada."""
    m = re.match(r"^([¡¿'\"]*)(.*?)([.,;:!?'\"]*)$", palabra)
    return m.group(1), m.group(2), m.group(3)


def aplicar_diccionario(oracion: str, df_nouns: pd.DataFrame, df_verbs: pd.DataFrame, df_adj: pd.DataFrame,
                          palabras_ambiguas: set, client,
                          max_reemplazos: int = 3, max_variantes: int = 2) -> list[tuple[str, list[str]]]:
    """
    Reglas de negocio:
    - Palabras ambiguas (aparecen en más de una tabla POS, ej. 'guasu')
      NUNCA son candidatas — se descartan gratis, sin llamar a la IA.
    - Si la oración tiene MENOS de 2 candidatos reales (ya sin
      ambiguas), se ignora entera.
    - Los candidatos se priorizan por "riqueza" (cuántos sinónimos
      alternativos existen realmente para esa palabra) — se usan
      primero los que tienen más opciones. Sustantivos y adjetivos
      tienen riqueza calculable directo del diccionario; los verbos
      quedan en 0 (no se puede saber sin llamar a Gemini por cada uno).
    - Hasta max_variantes oraciones de salida, cada una con hasta
      max_reemplazos palabras cambiadas A LA VEZ. Cada variante evita
      repetir un sinónimo ya usado en esa misma palabra (sustantivo,
      adjetivo Y verbo), Y evita coincidir exactamente con la oración
      original — si un intento no cambia nada de verdad, no cuenta.
    - Se preserva la puntuación pegada a la palabra (ej. el punto
      final de una oración) — se reemplaza solo el núcleo, no el
      signo de puntuación.

    Devuelve lista de (oracion_nueva, metodos_usados), 0 a max_variantes elementos.
    """
    palabras = oracion.split()
    clave_original = _normalizar_para_comparar(oracion)

    # 1. Encontrar candidatos reales — buscar_pos ya descarta ambiguas solo
    candidatos = []
    for idx, palabra in enumerate(palabras):
        _, nucleo, _ = _separar_puntuacion(palabra)
        pos, fila = buscar_pos(nucleo, df_nouns, df_verbs, df_adj, palabras_ambiguas)
        if not pos:
            continue
        if pos == "sustantivo":
            riqueza = contar_alternativas_sustantivo(nucleo, df_nouns)
        elif pos == "adjetivo":
            riqueza = contar_alternativas_adjetivo(nucleo, df_adj)
        else:
            riqueza = 0
        candidatos.append({"idx": idx, "pos": pos, "fila": fila, "palabra": nucleo, "riqueza": riqueza})

    if len(candidatos) < 2:
        return []  # se ignora: no vale la pena con 1 solo candidato

    # 2. Priorizar por riqueza (más alternativas primero)
    candidatos.sort(key=lambda c: c["riqueza"], reverse=True)
    candidatos_a_usar = candidatos[:max_reemplazos]

    # 3. Generar hasta max_variantes oraciones, evitando repetir sinónimo por palabra
    variantes = []
    sinonimos_usados_por_idx = {}

    for _ in range(max_variantes):
        palabras_nuevas = palabras.copy()
        metodos = []

        for c in candidatos_a_usar:
            usados = sinonimos_usados_por_idx.get(c["idx"], set())
            prefijo, nucleo_original, sufijo = _separar_puntuacion(palabras[c["idx"]])

            if c["pos"] == "sustantivo":
                nuevo = sinonimo_sustantivo(c["palabra"], df_nouns, excluir=usados)
                metodo = "sustantivo"
            elif c["pos"] == "adjetivo":
                nuevo = sinonimo_adjetivo(c["palabra"], df_adj, excluir=usados)
                metodo = "adjetivo"
            else:  # verbo
                intentos_verbo = 0
                nuevo = None
                while intentos_verbo < 3:  # hasta 3 intentos de conseguir un sinónimo NO repetido
                    lema_nuevo = pedir_sinonimo_verbo_es(c["fila"]["espanol_lema"], client)
                    candidato_verbo = conjugar_verbo(
                        lema_nuevo, c["fila"]["modo"], c["fila"]["tiempo"], c["fila"]["persona"], c["fila"]["numero"], df_verbs
                    )
                    intentos_verbo += 1
                    if candidato_verbo and candidato_verbo not in usados and candidato_verbo != nucleo_original:
                        nuevo = candidato_verbo
                        break
                metodo = "verbo"

            # No aceptar si el "reemplazo" es igual a la palabra original —
            # eso no es un cambio real, aunque técnicamente algo se generó.
            if nuevo and nuevo != nucleo_original:
                palabras_nuevas[c["idx"]] = f"{prefijo}{nuevo}{sufijo}"  # se preserva la puntuación
                metodos.append(metodo)
                sinonimos_usados_por_idx.setdefault(c["idx"], set()).add(nuevo)

        if not metodos:
            continue

        texto_nuevo = " ".join(palabras_nuevas)
        clave = _normalizar_para_comparar(texto_nuevo)

        if clave == clave_original:
            continue  # idéntica a la oración ORIGINAL — no es una variante real
        if clave in [_normalizar_para_comparar(v[0]) for v in variantes]:
            continue  # idéntica a una variante ya generada en esta corrida

        variantes.append((texto_nuevo, metodos))

    return variantes


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
    df_nouns, df_verbs, df_adj = cargar_diccionarios()
    print(f"Sustantivos: {len(df_nouns)} filas. Verbos: {len(df_verbs)} filas. Adjetivos: {len(df_adj)} filas.")

    palabras_ambiguas = calcular_palabras_ambiguas(df_nouns, df_verbs, df_adj)
    print(f"Palabras ambiguas detectadas (aparecen en 2+ tablas, se excluyen): {len(palabras_ambiguas)}")

    print("\n=== Aplicando diccionario (ignora oraciones con <2 candidatos; hasta 2 variantes, "
          "hasta 3 reemplazos simultáneos c/u) ===")
    registros = []
    ignoradas_por_pocos_candidatos = 0
    for item in oraciones:
        variantes = aplicar_diccionario(item["texto"], df_nouns, df_verbs, df_adj, palabras_ambiguas, client,
                                          max_reemplazos=3, max_variantes=2)
        if not variantes:
            ignoradas_por_pocos_candidatos += 1
            continue
        for texto_nuevo, metodos in variantes:
            registros.append({
                "texto": texto_nuevo,
                "texto_base": item["texto"],
                "tipo_transformacion": f"diccionario_{len(metodos)}reemplazos",
                "detalle_reemplazos": metodos,
                "dominio": item.get("dominio", "sin_clasificar"),
                "estrategia": "3",
            })

    print(f"\n{len(registros)} variantes generadas "
          f"({ignoradas_por_pocos_candidatos} oraciones ignoradas por tener menos de 2 candidatos).")
    guardar(registros)