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

CARPETA_RAW_RAIZ = "raw"
CARPETA_BASE_ESTRATEGIA5 = os.path.join("raw", "estrategia5")
CARPETA_BASE_E3 = os.path.join("raw", "estrategia3")

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

# ── MODO PRUEBA ──
# Menú interactivo que elige qué lote de la raíz de raw/ procesar.
# LIMITE_PRUEBA / LIMITE_ORACIONES_PRUEBA en 0 = SIN límites (procesa
# todas las oraciones del archivo elegido y guarda todo lo que salga).
MODO_PRUEBA = True
FUENTE_PRUEBA = "flores-200.jsonl"
LIMITE_PRUEBA = 0
LIMITE_ORACIONES_PRUEBA = 0
SEMILLA_PRUEBA = 42

# ─────────────────────────────────────────────────────────────
# Configuración por fuente: viene de config_por_fuente.py, compartida
# con run_strategy_3.py — no se duplica el criterio en dos lugares.
# ─────────────────────────────────────────────────────────────
from config_por_fuente import config_para_fuente


# ─────────────────────────────────────────────────────────────
# Leer las oraciones base de la Estrategia 5.
# Por defecto toma TODOS los .jsonl que encuentre en CARPETA_BASE_ESTRATEGIA5
# (recursivo, por si están organizados en subcarpetas por fuente).
# Con ultimos_n_archivos, en cambio, toma solo los N más recientes por
# fecha de modificación — útil cuando hay archivos ya afinados/tocados
# a mano en la raíz de raw/ y no querés releer todo el historial viejo.
# Ajustá CARPETA_BASE_ESTRATEGIA5 arriba según dónde estén esos archivos.
# ─────────────────────────────────────────────────────────────
def _leer_primera_fila_seed_file(archivo: str) -> str:
    """
    Lee SOLO la primera línea del archivo para determinar su fuente,
    sin cargar el archivo entero — esto es lo que decide si conviene
    leer ese lote completo, no es solo para mostrar.
    """
    with open(archivo, "r", encoding="utf-8") as f:
        primera_linea = f.readline().strip()
    if not primera_linea:
        return "desconocido"
    try:
        primer_registro = json.loads(primera_linea)
    except json.JSONDecodeError:
        return "desconocido"
    return primer_registro.get("seed_file", "desconocido")


def buscar_archivos_por_fuente(solo_raiz: bool = False) -> dict[str, list[str]]:
    """
    Encuentra todos los .jsonl candidatos (en cualquiera de las
    ubicaciones posibles) y, leyendo SOLO la primera fila de cada uno,
    determina de qué fuente es — sin cargar ningún archivo completo
    todavía. Devuelve {fuente: [rutas de archivos]}.

    solo_raiz=True busca únicamente raw/estrategia5_lote_*.jsonl (los
    lotes sueltos en la raíz de raw/), sin tocar las subcarpetas de
    raw/estrategia5/<fuente>/ — útil para el MODO PRUEBA.
    """
    if solo_raiz:
        patrones = [
            os.path.join(CARPETA_RAW_RAIZ, "estrategia5_lote_*.jsonl"),
        ]
    else:
        patrones = [
            os.path.join(CARPETA_BASE_ESTRATEGIA5, "**", "*.jsonl"),
            os.path.join(CARPETA_RAW_RAIZ, "estrategia5_lote_*.jsonl"),
            os.path.join(CARPETA_RAW_RAIZ, "*.jsonl"),
        ]
    print(f"[DEBUG] Buscando en (rutas absolutas):")
    for patron in patrones:
        print(f"  - {os.path.abspath(patron)}")

    archivos = set()
    for patron in patrones:
        archivos.update(glob.glob(patron, recursive=True))

    print(f"[DEBUG] Archivos .jsonl encontrados en total: {len(archivos)}")

    if not archivos:
        raise FileNotFoundError(
            f"No hay nada en {os.path.abspath(CARPETA_BASE_ESTRATEGIA5)}/ ni en "
            f"{os.path.abspath(CARPETA_RAW_RAIZ)}/. Corré primero generar_estrategia_5(), "
            f"o revisá que estés parada en la carpeta correcta al ejecutar el script."
        )

    agrupado: dict[str, list[str]] = {}
    for archivo in sorted(archivos):
        fuente = _leer_primera_fila_seed_file(archivo)
        print(f"  [DEBUG] {archivo}  →  seed_file detectado: '{fuente}'")
        agrupado.setdefault(fuente, []).append(archivo)
    return agrupado


def elegir_fuente_interactivo(agrupado: dict[str, list[str]]) -> str | None:
    """
    Menú OPCIONAL — elegí una fuente entre las detectadas (por primera
    fila de cada archivo, ya verificada). Devuelve el nombre de la
    fuente elegida, o None si se elige "todas".
    """
    fuentes = sorted(agrupado.keys())
    print("\n=== ¿Con qué fuente querés trabajar? ===")
    print("  [0] Todas las fuentes")
    for i, fuente in enumerate(fuentes, 1):
        print(f"  [{i}] {fuente}  —  {len(agrupado[fuente])} archivo(s) detectado(s)")

    while True:
        opcion = input(f"\nElegí un número (0-{len(fuentes)}): ").strip()
        try:
            idx = int(opcion)
        except ValueError:
            print("  Ingresá un número válido.")
            continue
        if idx == 0:
            return None
        if 1 <= idx <= len(fuentes):
            return fuentes[idx - 1]
        print(f"  Ingresá un número entre 0 y {len(fuentes)}.")


def _resumen_archivo_root(archivo: str) -> tuple[str, int, str]:
    """(seed_file, cantidad de oraciones, primera oración) — lee el archivo
    una sola vez y aprovecha la primera fila para el seed_file."""
    seed = _leer_primera_fila_seed_file(archivo)
    n = 0
    primera = ""
    with open(archivo, "r", encoding="utf-8") as f:
        for linea in f:
            n += 1
            if n == 1:
                try:
                    primera = json.loads(linea).get("texto", "")[:60]
                except json.JSONDecodeError:
                    primera = ""
    return seed, n, primera


def elegir_archivo_root_interactivo(archivos: list[str]) -> str | None:
    """
    Menú interactivo sobre los lotes de Estrategia 5 en la raíz de raw/
    (raw/estrategia5_lote_*.jsonl): muestra cada archivo con su fuente
    (seed_file) y cantidad de oraciones, y deja elegir uno — o TODOS.
    Devuelve la ruta del archivo elegido, o None si se elige "todos".
    """
    print("\n=== Lotes de Estrategia 5 en la raíz de raw/ ===")
    info = []
    for archivo in archivos:
        seed, n, primera = _resumen_archivo_root(archivo)
        info.append((archivo, seed, n, primera))
    print("  [0] TODOS los lotes (sin límites)")
    for i, (archivo, seed, n, primera) in enumerate(info, 1):
        print(f"  [{i}] {os.path.basename(archivo)}  —  {seed}  ({n} oraciones)")
        if primera:
            print(f"      {primera}...")
    while True:
        opcion = input(f"\nElegí un número (0-{len(info)}): ").strip()
        try:
            idx = int(opcion)
        except ValueError:
            print("  Ingresá un número válido.")
            continue
        if idx == 0:
            return None
        if 1 <= idx <= len(info):
            return info[idx - 1][0]
        print(f"  Ingresá un número entre 0 y {len(info)}.")


def leer_oraciones_de_fuente(agrupado: dict[str, list[str]], fuente: str | None) -> list[dict]:
    """
    Recién ACÁ se cargan los archivos completos — solo los que
    corresponden a la fuente elegida (ya confirmada por la primera
    fila). Si fuente es None, carga todos los archivos encontrados.
    """
    if fuente is None:
        archivos_a_leer = [a for lista in agrupado.values() for a in lista]
    else:
        archivos_a_leer = agrupado[fuente]

    print(f"[DEBUG] Fuente elegida: {fuente!r} → {len(archivos_a_leer)} archivo(s) a leer:")
    for a in archivos_a_leer:
        print(f"  - {a}")

    todas = []
    for archivo in sorted(archivos_a_leer):
        df = pd.read_json(archivo, lines=True)
        filas_antes = len(df)
        print(f"[DEBUG] {archivo}: {filas_antes} fila(s) crudas. Columnas: {list(df.columns)}")
        if "estrategia" in df.columns:
            # Comparar como texto, tolera que haya venido como número (5) en
            # vez de string ("5") — y filtra por FILA, no descarta el archivo
            # entero por una sola fila rara.
            df = df[df["estrategia"].astype(str) == "5"]
            if len(df) < filas_antes:
                print(f"  ⚠️  {archivo}: {filas_antes - len(df)} fila(s) descartada(s) "
                      f"por no ser de Estrategia 5 (de {filas_antes} totales).")
        else:
            print(f"  ⚠️  {archivo}: NO tiene columna 'estrategia' — no se filtró por eso.")
        if df.empty:
            print(f"  ⚠️  {archivo}: quedó VACÍO después del filtro, se descarta.")
            continue
        if "seed_file" not in df.columns:
            print(f"  ⚠️  {archivo}: NO tiene columna 'seed_file' — se marca 'desconocido'.")
            df["seed_file"] = "desconocido"
        print(f"  ✅ Leído completo: {archivo} ({len(df)} oraciones)")
        todas.append(df)

    if not todas:
        print("[DEBUG] 🚨 Ningún archivo sobrevivió los filtros — 'todas' está vacía, se devuelve [].")
        return []
    resultado = pd.concat(todas, ignore_index=True).to_dict("records")
    print(f"[DEBUG] Total final devuelto: {len(resultado)} oraciones.")
    return resultado


def leer_base_estrategia5(ultimos_n_archivos: int | None = None) -> list[dict]:
    """Función vieja, se mantiene por compatibilidad — el flujo nuevo
    usa buscar_archivos_por_fuente() + elegir_fuente_interactivo() +
    leer_oraciones_de_fuente()."""
    # Buscamos en TODAS las variantes de ubicación posibles — la fuente
    # real de verdad la da el campo "seed_file" DENTRO del JSON, no la
    # carpeta donde terminó el archivo. Esto cubre: subcarpetas por
    # fuente (raw/estrategia5/<seed>/lote_*.jsonl), el patrón viejo
    # plano (raw/estrategia5_lote_*.jsonl) y cualquier .jsonl suelto
    # directo en raw/ (por si el otro dev generó ahí sin subcarpeta).
    patrones = [
        os.path.join(CARPETA_BASE_ESTRATEGIA5, "**", "*.jsonl"),      # raw/estrategia5/**/*.jsonl
        os.path.join(CARPETA_RAW_RAIZ, "estrategia5_lote_*.jsonl"),   # raw/estrategia5_lote_*.jsonl (viejo)
        os.path.join(CARPETA_RAW_RAIZ, "*.jsonl"),                    # raw/*.jsonl (suelto en la raíz)
    ]
    archivos = set()
    for patron in patrones:
        archivos.update(glob.glob(patron, recursive=True))
    archivos = list(archivos)

    if not archivos:
        raise FileNotFoundError(
            f"No hay nada en {CARPETA_BASE_ESTRATEGIA5}/ ni en {CARPETA_RAW_RAIZ}/. "
            f"Corré primero generar_estrategia_5()."
        )

    if ultimos_n_archivos:
        # Más recientes primero, y nos quedamos solo con los últimos N
        archivos.sort(key=os.path.getmtime, reverse=True)
        archivos = archivos[:ultimos_n_archivos]
        print(f"[Modo últimos N] Usando solo los {len(archivos)} archivo(s) más recientes "
              f"(por fecha de modificación):")
        for a in archivos:
            print(f"  - {a}")
        archivos = sorted(archivos)  # orden estable para procesar, no importa cuál primero
    else:
        archivos = sorted(archivos)

    todas = []
    for archivo in archivos:
        df = pd.read_json(archivo, lines=True)
        if "estrategia" in df.columns and (df["estrategia"] != "5").any():
            continue  # por si el patrón "raw/*.jsonl" agarró algo que no es de Estrategia 5
        if "seed_file" not in df.columns:
            df["seed_file"] = "desconocido"  # lotes viejos, de antes de este cambio
        print(f"  {archivo}: {len(df)} oraciones (fuente: {df['seed_file'].iloc[0] if len(df) else '—'})")
        todas.append(df)
    return pd.concat(todas, ignore_index=True).to_dict("records")


# ─────────────────────────────────────────────────────────────
# Diccionarios (sustantivos, verbos)
# ─────────────────────────────────────────────────────────────
def cargar_diccionarios():
    try:
        df_nouns = pd.read_csv(RUTA_NOUNS, header=None, names=COLUMNAS_NOUNS, encoding="utf-8")
    except pd.errors.ParserError:
        print("  ⚠️  Filas malformadas detectadas en el CSV de sustantivos, saltando esas líneas...")
        df_nouns = pd.read_csv(
            RUTA_NOUNS, header=None, names=COLUMNAS_NOUNS, encoding="utf-8",
            engine="python", on_bad_lines="warn",
        )

    try:
        df_adj = pd.read_csv(RUTA_ADJ, header=None, names=COLUMNAS_ADJ, encoding="utf-8")
    except pd.errors.ParserError:
        print("  ⚠️  Filas malformadas detectadas en el CSV de adjetivos, saltando esas líneas...")
        df_adj = pd.read_csv(
            RUTA_ADJ, header=None, names=COLUMNAS_ADJ, encoding="utf-8",
            engine="python", on_bad_lines="warn",
        )

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

    print(f"[DEBUG] df_nouns: shape={df_nouns.shape}, columnas={list(df_nouns.columns)}")
    print(f"[DEBUG] df_verbs: shape={df_verbs.shape}, columnas={list(df_verbs.columns)}")
    print(f"[DEBUG] df_adj:   shape={df_adj.shape}, columnas={list(df_adj.columns)}")
    print(f"[DEBUG] Ruta nouns: {os.path.abspath(RUTA_NOUNS)}")
    print(f"[DEBUG] Ruta verbs: {os.path.abspath(RUTA_VERBS)}")
    print(f"[DEBUG] Ruta adj:   {os.path.abspath(RUTA_ADJ)}")

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


def _es_palabra_limpia(palabra: str) -> bool:
    """
    Descarta filas sucias del diccionario donde quedaron dos variantes
    juntas en una sola celda (ej. "yakã,_y'akã" en vez de dos filas
    separadas) — una palabra guaraní real no tiene coma ni guion bajo.
    """
    return "," not in palabra and "_" not in palabra


def sinonimo_sustantivo(palabra: str, df_nouns: pd.DataFrame, excluir: set | None = None) -> str | None:
    excluir = excluir or set()
    fila = df_nouns[df_nouns["guarani"] == palabra]
    if fila.empty:
        return None
    lema = fila.iloc[0]["espanol_lema"]
    candidatos = df_nouns[
        (df_nouns["espanol_lema"] == lema) & (~df_nouns["guarani"].isin({palabra} | excluir))
    ]
    candidatos = candidatos[candidatos["guarani"].apply(_es_palabra_limpia)]
    if candidatos.empty:
        return None
    return candidatos.sample(1).iloc[0]["guarani"]


def contar_alternativas_sustantivo(palabra: str, df_nouns: pd.DataFrame) -> int:
    """Cuántos sinónimos distintos existen realmente para esta palabra — usado para priorizar."""
    fila = df_nouns[df_nouns["guarani"] == palabra]
    if fila.empty:
        return 0
    lema = fila.iloc[0]["espanol_lema"]
    candidatos = df_nouns[(df_nouns["espanol_lema"] == lema) & (df_nouns["guarani"] != palabra)]
    candidatos = candidatos[candidatos["guarani"].apply(_es_palabra_limpia)]
    if candidatos.empty:
        return 0
    return candidatos["guarani"].nunique()


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
    candidatos = candidatos[candidatos["guarani"].apply(_es_palabra_limpia)]
    if candidatos.empty:
        return None
    return candidatos.sample(1).iloc[0]["guarani"]


def contar_alternativas_adjetivo(palabra: str, df_adj: pd.DataFrame) -> int:
    fila = df_adj[df_adj["guarani"] == palabra]
    if fila.empty:
        return 0
    lema = fila.iloc[0]["espanol_lema"]
    candidatos = df_adj[(df_adj["espanol_lema"] == lema) & (df_adj["guarani"] != palabra)]
    candidatos = candidatos[candidatos["guarani"].apply(_es_palabra_limpia)]
    if candidatos.empty:
        return 0
    return candidatos["guarani"].nunique()


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
    fila = fila[fila["guarani_forma"].notna() & (fila["guarani_forma"] != "")]
    if fila.empty:
        return None
    return fila.sample(1).iloc[0]["guarani_forma"]


def verificar_reemplazo_valido_en_contexto(oracion: str, palabra_original: str, palabra_nueva: str, client) -> bool:
    """
    Verifica que reemplazar 'palabra_original' por 'palabra_nueva' en
    ESTA oración específica mantenga el sentido correcto — resuelve
    casos de lemas españoles ambiguos (ej. "tenedor" = fork / holder)
    que agrupan dos palabras guaraní completamente distintas como si
    fueran sinónimos, sin serlo.

    Se le exige a Gemini que primero declare qué significa cada palabra
    EN ESTA oración (glosa corta) y después compare — para que no valide
    por "naturalidad" cambios que en realidad pierden el sentido (ej.
    "ñembosarái"=partido → "ñeha'ã"=prueba, comparten lema "juego").
    Solo se acepta una respuesta inequívoca "SI"; cualquier otra cosa
    (incluido error de API o respuesta vacía) se trata como NO para
    conservar la palabra original.
    """
    prompt = (
        f"Oración en guaraní: \"{oracion}\"\n\n"
        f"En ESTA oración:\n"
        f"1) ¿Qué significa exactamente '{palabra_original}'? (glosa corta en español)\n"
        f"2) ¿Qué significa exactamente '{palabra_nueva}'? (glosa corta en español)\n"
        f"3) ¿Significan lo mismo aquí (sinónimos reales en este contexto), o "
        f"'{palabra_nueva}' cambia el significado de la oración?\n\n"
        f"Respondé SOLO con una única palabra: SI o NO."
    )
    try:
        respuesta = client.models.generate_content(model="gemini-3.5-flash", contents=prompt)
        texto = (respuesta.text or "").strip().upper()
    except Exception:
        return False  # ante cualquier fallo de API, no se introduce un cambio no verificado
    if not texto:
        return False
    primera = "".join(c for c in texto.split()[0] if c.isalpha())
    primera = primera.replace("Í", "I")
    return primera == "SI"


def _distancia_edicion(a: str, b: str) -> int:
    """Distancia de Levenshtein — para detectar 'sinónimos' que en
    realidad son la misma palabra con una letra cambiada."""
    if a == b:
        return 0
    if len(a) > len(b):
        a, b = b, a
    fila_anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        fila_actual = [i]
        for j, cb in enumerate(b, 1):
            fila_actual.append(min(
                fila_anterior[j] + 1,
                fila_actual[j - 1] + 1,
                fila_anterior[j - 1] + (ca != cb),
            ))
        fila_anterior = fila_actual
    return fila_anterior[-1]


def _reemplazo_demasiado_parecido(original: str, nuevo: str) -> bool:
    """
    Rechaza reemplazos que son la MISMA palabra con una mínima diferencia
    ortográfica (ej. 'ojuhu' → 'ojohu', una sola vocal distinta): a simple
    vista parecen errores de tipeo, no variantes. Los sinónimos reales
    tienen que diferir en más de un carácter.
    """
    o = _normalizar_para_comparar(original)
    n = _normalizar_para_comparar(nuevo)
    if o == n:
        return True
    return _distancia_edicion(o, n) <= 1


def pedir_sinonimo_verbo_es(lema_original: str, client) -> str:
    prompt = (
        f"Dame UN sinónimo en español, en infinitivo, del verbo '{lema_original}'. "
        f"Respondé solo el infinitivo, una palabra, sin explicación."
    )
    response = client.models.generate_content(model="gemini-3.5-flash", contents=prompt)
    return (response.text or "").strip().lower()


import re


def _separar_puntuacion(palabra: str) -> tuple[str, str, str]:
    """Separa una palabra en (prefijo de puntuación, núcleo, sufijo de puntuación),
    para poder buscar/reemplazar el núcleo sin perder la puntuación pegada."""
    m = re.match(r"^([¡¿'\"]*)(.*?)([.,;:!?'\"]*)$", palabra)
    return m.group(1), m.group(2), m.group(3)


def aplicar_diccionario(oracion: str, df_nouns: pd.DataFrame, df_verbs: pd.DataFrame, df_adj: pd.DataFrame,
                          palabras_ambiguas: set, client, pos_permitidos: set,
                          max_reemplazos: int = 3, max_variantes: int = 1,
                          diagnostico: dict | None = None) -> list[tuple[str, list[str]]]:
    """
    Reglas de negocio:
    - Palabras ambiguas (aparecen en más de una tabla POS, ej. 'guasu')
      NUNCA son candidatas — se descartan gratis, sin llamar a la IA.
    - Solo se consideran categorías gramaticales en pos_permitidos —
      ej. para jojajovai.jsonl (registro periodístico), 'verbo' está
      excluido por decisión humana, aunque el diccionario lo encuentre.
    - Si la oración NO tiene ningún candidato real, se ignora entera.
      Con 1 solo candidato SÍ se genera igual — no hace falta mínimo 2.
    - Los candidatos se priorizan por "riqueza" (cuántos sinónimos
      alternativos existen realmente para esa palabra) — se usan
      primero los que tienen más opciones. Sustantivos y adjetivos
      tienen riqueza calculable directo del diccionario; los verbos
      quedan en 0 (no se puede saber sin llamar a Gemini por cada uno).
    - Por default, UNA sola oración de salida por base (max_variantes=1),
      con hasta max_reemplazos palabras cambiadas A LA VEZ — esto es lo
      que evita la repetición real: no generar una 2da variante débil
      de la misma base.
    - Se preserva la puntuación pegada a la palabra (ej. el punto
      final de una oración) — se reemplaza solo el núcleo, no el
      signo de puntuación.

    Devuelve lista de (oracion_nueva, metodos_usados), 0 a max_variantes elementos.
    """
    palabras = oracion.split()
    clave_original = _normalizar_para_comparar(oracion)

    # 1. Encontrar candidatos reales — buscar_pos ya descarta ambiguas solo
    candidatos = []
    if diagnostico is None:
        diagnostico = {}
    for clave in ["palabras_totales", "ambiguas", "no_en_diccionario", "pos_no_permitido", "sin_riqueza", "candidatos_validos"]:
        diagnostico.setdefault(clave, 0)

    for idx, palabra in enumerate(palabras):
        _, nucleo, _ = _separar_puntuacion(palabra)
        diagnostico["palabras_totales"] += 1

        if nucleo in palabras_ambiguas:
            diagnostico["ambiguas"] += 1
            continue

        pos, fila = buscar_pos(nucleo, df_nouns, df_verbs, df_adj, palabras_ambiguas)
        if not pos:
            diagnostico["no_en_diccionario"] += 1
            continue
        if pos not in pos_permitidos:
            diagnostico["pos_no_permitido"] += 1
            continue  # categoría no habilitada para esta fuente (ej. sin verbo en jojajovai)

        if pos == "sustantivo":
            riqueza = contar_alternativas_sustantivo(nucleo, df_nouns)
            if riqueza == 0:
                diagnostico["sin_riqueza"] += 1
                continue  # esta palabra puntual NO tiene ningún sinónimo real
        elif pos == "adjetivo":
            riqueza = contar_alternativas_adjetivo(nucleo, df_adj)
            if riqueza == 0:
                diagnostico["sin_riqueza"] += 1
                continue  # ídem
        else:  # verbo — no se puede saber de antemano sin llamar a Gemini, queda como candidato
            riqueza = 0

        diagnostico["candidatos_validos"] += 1
        candidatos.append({"idx": idx, "pos": pos, "fila": fila, "palabra": nucleo, "riqueza": riqueza})

    if len(candidatos) < 1:
        return []  # se ignora solo si NO hay ni un candidato real

    # 2. Priorizar por riqueza (más alternativas primero)
    candidatos.sort(key=lambda c: c["riqueza"], reverse=True)
    candidatos_a_usar = candidatos[:max_reemplazos]

    # 3. Generar UNA sola oración de salida por base (max_variantes=1 por
    # default) — esto es lo que evita la repetición real: no generar 2
    # variantes de la misma base donde la segunda es un cambio débil.
    variantes = []
    sinonimos_usados_por_idx = {}

    for _ in range(max_variantes):
        palabras_nuevas = palabras.copy()
        metodos = []

        # Palabras que YA están en la oración (todas, normalizadas) —
        # para no elegir un sinónimo que ya aparece en otra parte,
        # aunque sea válido, y termine repitiéndose (ej. "tĩsyry ha tĩsyry").
        palabras_en_oracion = {
            _separar_puntuacion(p)[1].lower() for p in palabras_nuevas
        }

        for c in candidatos_a_usar:
            usados = sinonimos_usados_por_idx.get(c["idx"], set()) | palabras_en_oracion
            prefijo, nucleo_original, sufijo = _separar_puntuacion(palabras[c["idx"]])

            nuevo = None
            metodo = c["pos"]
            intentos = 0
            max_intentos = 3

            while intentos < max_intentos and nuevo is None:
                intentos += 1

                if c["pos"] == "sustantivo":
                    candidato = sinonimo_sustantivo(c["palabra"], df_nouns, excluir=usados)
                elif c["pos"] == "adjetivo":
                    candidato = sinonimo_adjetivo(c["palabra"], df_adj, excluir=usados)
                else:  # verbo
                    lema_nuevo = pedir_sinonimo_verbo_es(c["fila"]["espanol_lema"], client)
                    candidato = conjugar_verbo(
                        lema_nuevo, c["fila"]["modo"], c["fila"]["tiempo"],
                        c["fila"]["persona"], c["fila"]["numero"], df_verbs
                    )
                    if isinstance(candidato, str) and candidato and _reemplazo_demasiado_parecido(nucleo_original, candidato):
                        usados = usados | {candidato.lower()}
                        continue  # es la misma palabra con una letra cambiada (ej. ojuhu→ojohu)

                if not isinstance(candidato, str) or not candidato or candidato == nucleo_original or candidato.lower() in usados:
                    if isinstance(candidato, str) and candidato:
                        usados = usados | {candidato.lower()}
                    continue  # este candidato no sirve, probar otro en el próximo intento

                # Verificación de CONTEXTO — acá se ataca directo el caso
                # "tenedor" (fork vs. holder): dos palabras guaraní
                # totalmente distintas comparten lema español ambiguo.
                # Se verifica el reemplazo específico propuesto, no cada
                # candidato de la oración — más barato que la versión
                # anterior, y ataca justo el problema real encontrado.
                if verificar_reemplazo_valido_en_contexto(oracion, nucleo_original, candidato, client):
                    nuevo = candidato
                else:
                    usados = usados | {candidato.lower()}  # descartado por contexto, no reintentar el mismo

            # No aceptar si el "reemplazo" es igual a la palabra original —
            # eso no es un cambio real, aunque técnicamente algo se generó.
            if nuevo and nuevo != nucleo_original:
                palabras_nuevas[c["idx"]] = f"{prefijo}{nuevo}{sufijo}"  # se preserva la puntuación
                metodos.append(metodo)
                sinonimos_usados_por_idx.setdefault(c["idx"], set()).add(nuevo.lower())
                palabras_en_oracion.add(nuevo.lower())  # ya no lo vuelve a elegir para OTRA palabra de esta misma variante

        # Se acepta con 1 solo reemplazo si es lo único disponible —
        # lo que YA no se repite es la oración de salida (max_variantes=1).
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
def guardar(registros: list[dict]) -> list[str]:
    if not registros:
        print("Nada que guardar (0 registros) — no se crea archivo.")
        return []

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    agrupados: dict[str, list[dict]] = {}
    for reg in registros:
        seed = reg.get("seed_file", "") or "(sin_seed)"
        agrupados.setdefault(seed, []).append(reg)

    rutas = []
    for seed, grupo in agrupados.items():
        if seed != "(sin_seed)":
            seed_stem = os.path.splitext(os.path.basename(seed))[0]
        else:
            seed_stem = "(sin_seed)"
        carpeta = os.path.join(CARPETA_BASE_E3, seed_stem, "sinonimo")
        os.makedirs(carpeta, exist_ok=True)
        ruta = os.path.join(carpeta, f"lote_{timestamp}.jsonl")
        with open(ruta, "w", encoding="utf-8") as f:
            for reg in grupo:
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        print(f"Guardado: {ruta} ({len(grupo)} registros)")
        rutas.append(ruta)
    return rutas


# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        raise ValueError("Falta GEMINI_API_KEY o API_KEY en el .env")
    client = genai.Client(api_key=api_key)

    print("=== Detectando fuentes disponibles (leyendo solo la primera fila de cada archivo) ===")
    if MODO_PRUEBA:
        archivos_root = sorted(glob.glob(os.path.join(CARPETA_RAW_RAIZ, "estrategia5_lote_*.jsonl")))
        if not archivos_root:
            raise FileNotFoundError(
                f"No hay lotes en la raíz de raw/ ({os.path.join(CARPETA_RAW_RAIZ, 'estrategia5_lote_*.jsonl')})."
            )
        seleccion = elegir_archivo_root_interactivo(archivos_root)
        archivos_a_leer = archivos_root if seleccion is None else [seleccion]
        etiqueta = "TODOS los lotes de la raíz" if seleccion is None else os.path.basename(seleccion)
        print(f"\n📦 Procesando: {etiqueta} — {len(archivos_a_leer)} archivo(s), "
              f"SIN límites de oraciones ni de variantes.")
        agrupado = {"raiz": archivos_a_leer}
        fuente_elegida = "raiz"
    else:
        agrupado = buscar_archivos_por_fuente(solo_raiz=False)
        for fuente, archivos in agrupado.items():
            print(f"  {fuente}: {len(archivos)} archivo(s)")
        fuente_elegida = elegir_fuente_interactivo(agrupado)
    print(f"\n=== Cargando datos completos ({'todas las fuentes' if fuente_elegida is None else fuente_elegida}) ===")
    oraciones = leer_oraciones_de_fuente(agrupado, fuente_elegida)
    print(f"Total: {len(oraciones)} oraciones base")

    if MODO_PRUEBA and LIMITE_ORACIONES_PRUEBA and len(oraciones) > LIMITE_ORACIONES_PRUEBA:
        # Muestra aleatoria con semilla fija (reproducible) en vez de las
        # primeras N: el inicio de flores-200 es casi todo salud/tecnología
        # y casi no da sustantivos — la muestra toca todos los dominios y
        # el lote de prueba no sale pobre y repetido.
        random.seed(SEMILLA_PRUEBA)
        oraciones = random.sample(oraciones, LIMITE_ORACIONES_PRUEBA)
        print(f"  🧪 MODO PRUEBA: muestra aleatoria de {len(oraciones)} oraciones "
              f"(semilla {SEMILLA_PRUEBA}).")

    print("\n=== Cargando diccionarios ===")
    df_nouns, df_verbs, df_adj = cargar_diccionarios()
    print(f"Sustantivos: {len(df_nouns)} filas. Verbos: {len(df_verbs)} filas. Adjetivos: {len(df_adj)} filas.")

    palabras_ambiguas = calcular_palabras_ambiguas(df_nouns, df_verbs, df_adj)
    print(f"Palabras ambiguas detectadas (aparecen en 2+ tablas, se excluyen): {len(palabras_ambiguas)}")

    print("\n=== Aplicando diccionario (ignora oraciones con <2 candidatos; hasta 2 variantes, "
          "hasta 3 reemplazos simultáneos c/u; según config por fuente) ===")
    registros = []
    ignoradas_por_pocos_candidatos = 0
    ignoradas_por_config_fuente = 0
    diagnostico = {}
    total = len(oraciones)
    for i, item in enumerate(oraciones, 1):
        print(f"  [{i}/{total}] {item['texto'][:70]}", flush=True)
        fuente = item.get("seed_file", "desconocido")
        config = config_para_fuente(fuente)

        if not config["sinonimos_habilitado"]:
            ignoradas_por_config_fuente += 1
            continue

        variantes = aplicar_diccionario(
            item["texto"], df_nouns, df_verbs, df_adj, palabras_ambiguas, client,
            pos_permitidos=config["pos_permitidos"],
            max_reemplazos=3, max_variantes=1,
            diagnostico=diagnostico,
        )
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
                "seed_file": fuente,
                "estrategia": "3",
            })
        if MODO_PRUEBA and LIMITE_PRUEBA and len(registros) >= LIMITE_PRUEBA:
            print(f"  🧪 MODO PRUEBA: alcanzadas {LIMITE_PRUEBA} variantes, cortando acá.")
            break

    print(f"\n{len(registros)} variantes generadas | "
          f"{ignoradas_por_pocos_candidatos} oraciones ignoradas por <2 candidatos | "
          f"{ignoradas_por_config_fuente} ignoradas por config de fuente (sinónimos deshabilitados).")

    print("\n=== Diagnóstico palabra por palabra (por qué NO se usaron como candidato) ===")
    print(f"  Palabras totales revisadas:        {diagnostico.get('palabras_totales', 0)}")
    print(f"  Ambiguas (2+ tablas, descartadas):  {diagnostico.get('ambiguas', 0)}")
    print(f"  No están en ningún diccionario:     {diagnostico.get('no_en_diccionario', 0)}")
    print(f"  Categoría no permitida por fuente:  {diagnostico.get('pos_no_permitido', 0)}")
    print(f"  Sin ningún sinónimo real (riqueza=0): {diagnostico.get('sin_riqueza', 0)}")
    print(f"  Candidatos válidos encontrados:      {diagnostico.get('candidatos_validos', 0)}")
    if diagnostico.get("candidatos_validos", 0) == 0:
        print("\n  🚨 CERO candidatos válidos en todo el lote — por eso el archivo salió vacío.")
        if diagnostico.get("pos_no_permitido", 0) > diagnostico.get("candidatos_validos", 0):
            print("     Sospecha principal: revisá pos_permitidos en config_por_fuente.py — "
                  "puede tener un error de tipeo (ej. 'verbos' en vez de 'verbo').")
    guardar(registros)