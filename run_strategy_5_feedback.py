"""
run_strategy_5_feedback.py
==========================
Lee los archivos de la carpeta feedback/estrategia5/, regenera las oraciones
incorrectas y genera nuevas, incorporando los errores detectados como
instrucción adicional en el prompt. Devuelve un JSONL unificado con:
  - tipo: "original"    → oración que ya estaba bien (sin cambios)
  - tipo: "regenerada"  → oración incorrecta re-generada con feedback
  - tipo: "nueva"       → oración adicional generada con el prompt+feedback
"""

import os
import sys
import json
import time
import glob
from datetime import datetime
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

# ─────────────────────────────────────────────────────────────
# Configuración
# ─────────────────────────────────────────────────────────────
FEEDBACK_DIR = os.path.join("feedback", "estrategia5")
RAW_DIR      = os.path.join("raw", "estrategia5")
NUEVAS_POR_TANDA = 3   # cuántas oraciones nuevas generar además de las regeneradas
MODEL = "gemini-3.5-flash"


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def cargar_feedbacks() -> list[dict]:
    """Lee todos los JSONL de feedback y devuelve una lista de entradas."""
    entradas = []
    patron = os.path.join(FEEDBACK_DIR, "para_regenerar_*.jsonl")
    archivos = glob.glob(patron)
    if not archivos:
        print(f"[Error] No se encontraron archivos en {FEEDBACK_DIR}")
        sys.exit(1)
    for archivo in sorted(archivos):
        with open(archivo, "r", encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if linea:
                    entradas.append(json.loads(linea))
    print(f"[Info] {len(entradas)} tanda(s) de feedback cargadas desde {len(archivos)} archivo(s).")
    return entradas


def construir_prompt_con_feedback(prompt_original: str, errores: list[dict]) -> str:
    """
    Toma el prompt original y agrega al final una sección con:
      - Lista de errores específicos a evitar (con ejemplo incorrecto → correcto)
      - Confirmación de que el resto está bien hecho
    """
    if not errores:
        return prompt_original

    # Separar cuerpo de la instrucción final
    lineas = prompt_original.rstrip().rsplit("\n", 1)
    cuerpo = lineas[0]
    instruccion_final = lineas[1] if len(lineas) > 1 else ""

    # Construir lista de errores únicos
    lineas_errores = []
    tipos_vistos = set()
    for err in errores:
        tipo   = err.get("tipo_error", "").strip()
        texto  = err.get("texto", "").strip()
        correc = err.get("correccion", "").strip()
        if tipo and tipo not in tipos_vistos:
            tipos_vistos.add(tipo)
            lineas_errores.append(f"  - {tipo}")
            if texto and correc and texto != correc:
                lineas_errores.append(f"    Incorrecto: {texto}")
                lineas_errores.append(f"    Correcto:   {correc}")

    bloque_feedback = (
        "\n\n---\n"
        "CORRECCIONES IMPORTANTES — errores detectados en generaciones anteriores que DEBES evitar:\n"
        + "\n".join(lineas_errores)
        + "\n\n"
        "El resto de la generacion estuvo bien hecha: el vocabulario, la estructura oracional, "
        "el estilo natural del guarani paraguayo y la adaptacion al dominio fueron correctos. "
        "Mantene ese nivel de calidad.\n"
        "---\n\n"
        + instruccion_final
    )

    return cuerpo + bloque_feedback


def llamar_api(client, prompt: str, max_reintentos: int = 4, espera_inicial: float = 5.0) -> str:
    """Llama a la API de Gemini con reintentos exponenciales."""
    from google.genai.errors import ServerError
    for intento in range(1, max_reintentos + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
            )
            return response.text.strip()
        except ServerError as e:
            if intento < max_reintentos:
                espera = espera_inicial * (2 ** (intento - 1))
                print(f"    [Reintento {intento}/{max_reintentos - 1}] Error 500. Esperando {espera:.0f}s...")
                time.sleep(espera)
            else:
                print(f"    [Error] Fallo tras {max_reintentos} intentos: {e}")
                raise


def guardar_lote(registros: list[dict], seed_stem: str) -> str:
    """Guarda el lote en raw/estrategia5/<seed>/lote_feedback_<timestamp>.jsonl"""
    carpeta = os.path.join(RAW_DIR, seed_stem)
    os.makedirs(carpeta, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta = os.path.join(carpeta, f"lote_feedback_{timestamp}.jsonl")
    with open(ruta, "w", encoding="utf-8") as f:
        for reg in registros:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")
    print(f"[OK] Lote guardado: {ruta} ({len(registros)} registros)")
    return ruta


# ─────────────────────────────────────────────────────────────
# Lógica principal
# ─────────────────────────────────────────────────────────────
def procesar_feedback(entrada: dict, client) -> tuple[list[dict], str]:
    """Procesa una entrada de feedback y devuelve la lista de registros resultantes."""
    seed_file   = entrada.get("seed_file", "")
    dominio     = entrada.get("dominio", "sin_clasificar")
    prompt_orig = entrada.get("prompt", "")
    total_orig  = entrada.get("total", 0)
    oraciones   = entrada.get("oraciones", [])

    seed_stem = os.path.splitext(seed_file)[0] if seed_file else "sin_seed"
    errores   = [o for o in oraciones if o.get("tipo_error")]

    print(f"\n  Seed: {seed_stem or '(sin seed)'}  |  Dominio: {dominio}")
    print(f"  Oraciones con error: {len(errores)}  |  Oraciones correctas originales: {total_orig - len(errores)}")

    prompt_feedback = construir_prompt_con_feedback(prompt_orig, errores)

    registros = []

    # 1) Nota sobre las oraciones originales correctas
    correctas = total_orig - len(errores)
    if correctas > 0:
        print(f"  -> {correctas} oraciones originales correctas (preservadas sin cambios)")
        registros.append({
            "nota":       f"{correctas} oraciones originales correctas de esta tanda fueron preservadas sin cambios.",
            "tipo":       "original",
            "dominio":    dominio,
            "estrategia": "5",
            "seed_file":  seed_file,
        })

    # 2) Regenerar las oraciones incorrectas
    if errores:
        print(f"  -> Regenerando {len(errores)} oraciones incorrectas...")
    for i, err in enumerate(errores, 1):
        tipo_error  = err.get("tipo_error", "")
        texto_inc   = err.get("texto", "")
        correc_ref  = err.get("correccion", "")
        print(f"    [{i}/{len(errores)}] {tipo_error[:70]}...")
        texto_nuevo = llamar_api(client, prompt_feedback)
        registros.append({
            "texto":            texto_nuevo,
            "texto_incorrecto": texto_inc,
            "tipo_error":       tipo_error,
            "correccion_ref":   correc_ref,
            "tipo":             "regenerada",
            "dominio":          dominio,
            "estrategia":       "5",
            "seed_file":        seed_file,
            "prompt":           prompt_feedback,
        })

    # 3) Generar N oraciones nuevas con el prompt+feedback
    print(f"  -> Generando {NUEVAS_POR_TANDA} oraciones nuevas con feedback incorporado...")
    for i in range(1, NUEVAS_POR_TANDA + 1):
        print(f"    [nueva {i}/{NUEVAS_POR_TANDA}]...")
        texto_nuevo = llamar_api(client, prompt_feedback)
        registros.append({
            "texto":      texto_nuevo,
            "tipo":       "nueva",
            "dominio":    dominio,
            "estrategia": "5",
            "seed_file":  seed_file,
            "prompt":     prompt_feedback,
        })

    return registros, seed_stem


def main():
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        print("[Error] Falta GEMINI_API_KEY en el .env")
        sys.exit(1)
    client = genai.Client(api_key=api_key)

    print("=== Estrategia 5 — Regeneracion con Feedback ===\n")

    entradas = cargar_feedbacks()

    # Agrupar por seed para guardar en carpetas separadas
    por_seed: dict[str, list[dict]] = {}
    for entrada in entradas:
        seed_file = entrada.get("seed_file", "")
        seed_stem = os.path.splitext(seed_file)[0] if seed_file else "sin_seed"
        por_seed.setdefault(seed_stem, []).append(entrada)

    total_seeds = len(por_seed)
    print(f"[Info] Seeds con feedback: {', '.join(por_seed.keys())}\n")

    for idx_seed, (seed_stem, tandas) in enumerate(por_seed.items(), 1):
        print(f"{'='*60}")
        print(f"[{idx_seed}/{total_seeds}] Procesando seed: {seed_stem} ({len(tandas)} tanda(s))")
        todos_registros = []

        for entrada in tandas:
            registros, _ = procesar_feedback(entrada, client)
            todos_registros.extend(registros)

        guardar_lote(todos_registros, seed_stem)

    print("\n=== Completado. ===")


if __name__ == "__main__":
    main()
