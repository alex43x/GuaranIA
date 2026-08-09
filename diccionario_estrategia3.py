"""
diccionario_estrategia3.py
==============================
Genera transformaciones de SINÓNIMOS sobre las oraciones base de E5
que YA fueron procesadas por run_strategy_3.py (reordenar). Lee desde
procesados_estrategia_3/reordenar/ y guarda en raw/estrategia3/{seed}/sinonimo/.

Mismo flujo de entrada que run_strategy_3.py: selector interactivo de seeds.

Requisitos: pip install google-genai pandas python-dotenv --break-system-packages
Necesita: .env con GEMINI_API_KEY, y el repo SyntaxGrammar-es-gn
          clonado como carpeta hermana.
"""

import os
import glob
import random
import json
import re
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

CARPETA_BASE_E3 = os.path.join("raw", "estrategia3")
CARPETA_INSUMOS_SINONIMO = os.path.join("raw", "estrategia5", "procesados_estrategia_3", "reordenar")
PROCESADOS_E3_SINONIMO = os.path.join("raw", "estrategia5", "procesados_estrategia_3", "sinonimo")

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

from config_por_fuente import config_para_fuente
from workers import mapear_paralelo


# ─────────────────────────────────────────────────────────────
# ENTRADA — mismo patrón que run_strategy_3.py
# ─────────────────────────────────────────────────────────────

def listar_seeds_disponibles(carpeta: str | None = None) -> list[dict]:
    """Escanea la carpeta dada y devuelve info de seeds con archivos pendientes."""
    if carpeta is None:
        carpeta = CARPETA_INSUMOS_SINONIMO
    seeds: dict[str, dict] = {}

    if not os.path.exists(carpeta):
        return []

    patron = os.path.join(carpeta, "**", "*.jsonl")
    for path in sorted(glob.glob(patron, recursive=True)):
        seed_dir = os.path.basename(os.path.dirname(path))
        if not seed_dir or seed_dir == os.path.basename(carpeta):
            continue
        if seed_dir not in seeds:
            seeds[seed_dir] = {"nombre": seed_dir, "archivos": 0, "registros": 0}
        seeds[seed_dir]["archivos"] += 1
        try:
            with open(path, "r", encoding="utf-8") as f:
                seeds[seed_dir]["registros"] += sum(1 for ln in f if ln.strip())
        except Exception:
            pass

    return sorted(seeds.values(), key=lambda s: s["nombre"])


def selector_consola(seeds: list[dict]) -> list[str]:
    """Menú interactivo: el usuario elige seeds por número, coma o 'all'."""
    print("Seeds disponibles:\n")
    for i, s in enumerate(seeds, 1):
        print(f"  [{i}] {s['nombre']:<20s} {s['archivos']:>3d} archivo(s)  ({s['registros']:>5d} registros pendientes)")
    print()

    while True:
        entrada = input("Elegí (números separados por coma, 'all', o 'q' para salir): ").strip()
        if entrada.lower() in ("q", "quit", "exit"):
            print("Cancelado.")
            exit(0)
        if entrada.lower() == "all":
            return [s["nombre"] for s in seeds]

        elegidas = []
        errores = []
        for parte in entrada.split(","):
            parte = parte.strip()
            if not parte:
                continue
            if "-" in parte:
                try:
                    ini, fin = parte.split("-", 1)
                    for n in range(int(ini), int(fin) + 1):
                        if 1 <= n <= len(seeds):
                            elegidas.append(seeds[n - 1]["nombre"])
                        else:
                            errores.append(str(n))
                except ValueError:
                    errores.append(parte)
            else:
                try:
                    n = int(parte)
                    if 1 <= n <= len(seeds):
                        elegidas.append(seeds[n - 1]["nombre"])
                    else:
                        errores.append(str(n))
                except ValueError:
                    errores.append(parte)

        if errores:
            print(f"  Opciones no válidas: {', '.join(errores)}. Intentá de nuevo.\n")
            continue
        if not elegidas:
            print("  No seleccionaste ninguna seed. Intentá de nuevo.\n")
            continue

        unicas = []
        for s in elegidas:
            if s not in unicas:
                unicas.append(s)
        print(f"  Seleccionadas: {', '.join(unicas)}\n")
        return unicas


def listar_archivos_de_seeds(seeds: list[str], carpeta_base: str | None = None) -> list[str]:
    """Devuelve la lista de archivos .jsonl (ordenada) de las seeds elegidas."""
    carpeta = carpeta_base or CARPETA_INSUMOS_SINONIMO
    if not os.path.exists(carpeta):
        raise RuntimeError(f"No existe '{carpeta}'. ¿Ya ejecutaste run_strategy_3.py primero?")

    patron = os.path.join(carpeta, "**", "*.jsonl")
    archivos = sorted(glob.glob(patron, recursive=True))
    if seeds:
        archivos = [p for p in archivos if os.path.basename(os.path.dirname(p)) in seeds]
    return archivos


def cargar_registros_de_archivo(path: str) -> list[dict]:
    """Carga los registros utilizables (texto + dominio) de UN archivo .jsonl
    — la unidad de trabajo del loop lote-por-lote."""
    registros = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if "texto" in record and "dominio" in record:
                    registros.append({
                        "texto": record["texto"],
                        "dominio": record["dominio"],
                        "seed_file": record.get("seed_file", ""),
                    })
            except json.JSONDecodeError:
                continue
    return registros


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
    nouns_set = set(df_nouns["guarani"])
    verbs_set = set(df_verbs["guarani_forma"])
    adj_set = set(df_adj["guarani"])
    return (nouns_set & verbs_set) | (nouns_set & adj_set) | (verbs_set & adj_set)


def buscar_pos(palabra: str, df_nouns: pd.DataFrame, df_verbs: pd.DataFrame, df_adj: pd.DataFrame,
                palabras_ambiguas: set):
    if palabra in palabras_ambiguas:
        return None, None

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
    t = texto.lower().strip()
    t = re.sub(r"[.,;:!?¡¿'\"]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t


def _es_palabra_limpia(palabra: str) -> bool:
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
        return False
    if not texto:
        return False
    primera = "".join(c for c in texto.split()[0] if c.isalpha())
    primera = primera.replace("Í", "I")
    return primera == "SI"


def _distancia_edicion(a: str, b: str) -> int:
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


def _separar_puntuacion(palabra: str) -> tuple[str, str, str]:
    m = re.match(r"^([¡¿'\"]*)(.*?)([.,;:!?'\"]*)$", palabra)
    return m.group(1), m.group(2), m.group(3)


def aplicar_diccionario(oracion: str, df_nouns: pd.DataFrame, df_verbs: pd.DataFrame, df_adj: pd.DataFrame,
                          palabras_ambiguas: set, client, pos_permitidos: set,
                          max_reemplazos: int = 3, max_variantes: int = 1,
                          diagnostico: dict | None = None) -> list[tuple[str, list[str]]]:
    palabras = oracion.split()
    clave_original = _normalizar_para_comparar(oracion)

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
            continue

        if pos == "sustantivo":
            riqueza = contar_alternativas_sustantivo(nucleo, df_nouns)
            if riqueza == 0:
                diagnostico["sin_riqueza"] += 1
                continue
        elif pos == "adjetivo":
            riqueza = contar_alternativas_adjetivo(nucleo, df_adj)
            if riqueza == 0:
                diagnostico["sin_riqueza"] += 1
                continue
        else:
            riqueza = 0

        diagnostico["candidatos_validos"] += 1
        candidatos.append({"idx": idx, "pos": pos, "fila": fila, "palabra": nucleo, "riqueza": riqueza})

    if len(candidatos) < 1:
        return []

    candidatos.sort(key=lambda c: c["riqueza"], reverse=True)
    candidatos_a_usar = candidatos[:max_reemplazos]

    variantes = []
    sinonimos_usados_por_idx = {}

    for _ in range(max_variantes):
        palabras_nuevas = palabras.copy()
        metodos = []

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
                else:
                    lema_nuevo = pedir_sinonimo_verbo_es(c["fila"]["espanol_lema"], client)
                    candidato = conjugar_verbo(
                        lema_nuevo, c["fila"]["modo"], c["fila"]["tiempo"],
                        c["fila"]["persona"], c["fila"]["numero"], df_verbs
                    )
                    if isinstance(candidato, str) and candidato and _reemplazo_demasiado_parecido(nucleo_original, candidato):
                        usados = usados | {candidato.lower()}
                        continue

                if not isinstance(candidato, str) or not candidato or candidato == nucleo_original or candidato.lower() in usados:
                    if isinstance(candidato, str) and candidato:
                        usados = usados | {candidato.lower()}
                    continue

                if verificar_reemplazo_valido_en_contexto(oracion, nucleo_original, candidato, client):
                    nuevo = candidato
                else:
                    usados = usados | {candidato.lower()}

            if nuevo and nuevo != nucleo_original:
                palabras_nuevas[c["idx"]] = f"{prefijo}{nuevo}{sufijo}"
                metodos.append(metodo)
                sinonimos_usados_por_idx.setdefault(c["idx"], set()).add(nuevo.lower())
                palabras_en_oracion.add(nuevo.lower())

        if not metodos:
            continue

        texto_nuevo = " ".join(palabras_nuevas)
        clave = _normalizar_para_comparar(texto_nuevo)

        if clave == clave_original:
            continue
        if clave in [_normalizar_para_comparar(v[0]) for v in variantes]:
            continue

        variantes.append((texto_nuevo, metodos))

    return variantes


# ─────────────────────────────────────────────────────────────
# Guardar
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

    print("=== Diccionario Estrategia 3 — Sinónimos ===")
    print(f"Fuente: {CARPETA_INSUMOS_SINONIMO}/\n")

    disponibles = listar_seeds_disponibles()
    if not disponibles:
        raise RuntimeError(
            f"No hay archivos en '{CARPETA_INSUMOS_SINONIMO}/'. "
            f"Ejecutá run_strategy_3.py primero."
        )

    seleccionadas = selector_consola(disponibles)

    archivos = listar_archivos_de_seeds(seleccionadas)
    if not archivos:
        raise RuntimeError("No hay archivos utilizables para esas seeds.")

    print("\n=== Cargando diccionarios ===")
    df_nouns, df_verbs, df_adj = cargar_diccionarios()
    print(f"Sustantivos: {len(df_nouns)} filas. Verbos: {len(df_verbs)} filas. Adjetivos: {len(df_adj)} filas.")

    palabras_ambiguas = calcular_palabras_ambiguas(df_nouns, df_verbs, df_adj)
    print(f"Palabras ambiguas detectadas (aparecen en 2+ tablas, se excluyen): {len(palabras_ambiguas)}")

    # ── Loop lote-por-lote ───────────────────────────────────────
    # Igual que en run_strategy_3.py: se procesa UN archivo fuente por vez
    # (generar variantes, guardarlas, y RECIÉN AHÍ mover ese archivo a
    # procesados_estrategia_3/) en vez de juntar todos los archivos elegidos
    # y mover todo junto al final. Así, si el proceso se corta a mitad de
    # camino, los lotes ya cerrados no se vuelven a reprocesar ni duplicar.
    print(f"\n{len(archivos)} archivo(s) a procesar, uno por vez.\n")

    diagnostico_global = {}
    archivos_procesados = 0
    total_variantes = 0
    total_ignoradas_candidatos = 0
    total_ignoradas_config = 0

    for i, path in enumerate(archivos, 1):
        seed_dir = os.path.basename(os.path.dirname(path))
        print(f"\n=== Lote {i}/{len(archivos)}: {os.path.basename(path)} ({seed_dir}) ===")

        semillas = cargar_registros_de_archivo(path)
        if not semillas:
            print("  Sin registros utilizables en este archivo — se omite (no se mueve).")
            continue

        total = len(semillas)
        registros = []
        ignoradas_por_pocos_candidatos = 0
        ignoradas_por_config_fuente = 0

        def procesar_item(item: dict) -> dict:
            """Procesa UNA semilla contra el diccionario. Cada llamada usa su propio
            diagnostico local (no comparte el dict global) porque mapear_paralelo()
            corre esto en varios threads a la vez, y un dict mutado por += desde
            varios threads a la vez no es seguro. Se mergea todo en el thread
            principal después, al recorrer los resultados."""
            fuente = item.get("seed_file", "desconocido")
            config = config_para_fuente(fuente)
            resultado = {"item": item, "fuente": fuente, "diag": {}, "variantes": None, "deshabilitado": False}

            print(f"  → arrancando: \"{item['texto'][:70]}\"", flush=True)

            if not config["sinonimos_habilitado"]:
                resultado["deshabilitado"] = True
                return resultado

            resultado["variantes"] = aplicar_diccionario(
                item["texto"], df_nouns, df_verbs, df_adj, palabras_ambiguas, client,
                pos_permitidos=config["pos_permitidos"],
                max_reemplazos=3, max_variantes=1,
                diagnostico=resultado["diag"],
            )
            return resultado

        contador = {"completadas": 0}

        def al_completar(idx, item, resultado):
            contador["completadas"] += 1
            print(f"  [{contador['completadas']}/{total}] listo: \"{item['texto'][:70]}\"", flush=True)

        resultados = mapear_paralelo(semillas, procesar_item, on_completado=al_completar)

        for resultado in resultados:
            item = resultado["item"]
            for clave, valor in resultado["diag"].items():
                diagnostico_global[clave] = diagnostico_global.get(clave, 0) + valor

            if resultado["deshabilitado"]:
                ignoradas_por_config_fuente += 1
                continue

            variantes = resultado["variantes"]
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
                    "seed_file": resultado["fuente"],
                    "estrategia": "3",
                })

        print(f"  {len(registros)} variantes generadas | "
              f"{ignoradas_por_pocos_candidatos} ignoradas por <2 candidatos | "
              f"{ignoradas_por_config_fuente} ignoradas por config de fuente.")

        guardar(registros)

        # Mover ESTE archivo fuente ya procesado antes de pasar al siguiente.
        destino_dir = os.path.join(PROCESADOS_E3_SINONIMO, seed_dir)
        os.makedirs(destino_dir, exist_ok=True)
        destino = os.path.join(destino_dir, os.path.basename(path))
        os.rename(path, destino)
        print(f"  Movido a {destino}")

        archivos_procesados += 1
        total_variantes += len(registros)
        total_ignoradas_candidatos += ignoradas_por_pocos_candidatos
        total_ignoradas_config += ignoradas_por_config_fuente

    print("\n=== Diagnóstico palabra por palabra (acumulado) ===")
    print(f"  Palabras totales revisadas:        {diagnostico_global.get('palabras_totales', 0)}")
    print(f"  Ambiguas (2+ tablas, descartadas):  {diagnostico_global.get('ambiguas', 0)}")
    print(f"  No están en ningún diccionario:     {diagnostico_global.get('no_en_diccionario', 0)}")
    print(f"  Categoría no permitida por fuente:  {diagnostico_global.get('pos_no_permitido', 0)}")
    print(f"  Sin ningún sinónimo real (riqueza=0): {diagnostico_global.get('sin_riqueza', 0)}")
    print(f"  Candidatos válidos encontrados:      {diagnostico_global.get('candidatos_validos', 0)}")
    if diagnostico_global.get("candidatos_validos", 0) == 0:
        print("\n  🚨 CERO candidatos válidos en todo el batch.")
        if diagnostico_global.get("pos_no_permitido", 0) > diagnostico_global.get("candidatos_validos", 0):
            print("     Sospecha principal: revisá pos_permitidos en config_por_fuente.py — "
                  "puede tener un error de tipeo (ej. 'verbos' en vez de 'verbo').")

    print("\n=== Completado ===")
    print(f"    Archivos procesados: {archivos_procesados}/{len(archivos)}")
    print(f"    Total variantes generadas: {total_variantes} | "
          f"{total_ignoradas_candidatos} ignoradas por <2 candidatos | "
          f"{total_ignoradas_config} ignoradas por config de fuente.")
