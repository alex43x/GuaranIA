import os
import sys
import json
import random
import time
import argparse
from dotenv import load_dotenv

# Ensure UTF-8 output on Windows console
sys.stdout.reconfigure(encoding='utf-8')

# Load environment variables (GEMINI_API_KEY, etc.)
load_dotenv()

# Import the strategy function from the main module
from strategy_gemini_dev import generar_estrategia_5

# ─────────────────────────────────────────────────────────────
# Seed files disponibles con sus dominios más representados
# ─────────────────────────────────────────────────────────────
SEED_CATALOG = {
    "tatoeba.jsonl": {
        "description": "Tatoeba — frases cortas, vida cotidiana",
        "domains": ["vida cotidiana", "familia", "comida", "clima", "tiempo libre"],
        "max_seeds": 25,
    },
    "belele.jsonl": {
        "description": "Belele — preguntas y respuestas, educación, cultura",
        "domains": ["educación", "cultura", "tecnología", "ciencia", "música"],
        "max_seeds": 20,
    },
    "americasnli.jsonl": {
        "description": "AmericasNLI — inferencia natural, narrativa, hogar",
        "domains": ["vida cotidiana", "economía", "familia", "salud", "política"],
        "max_seeds": 25,
    },
    "flores-200.jsonl": {
        "description": "FLORES-200 — noticias y enciclopedia multidominio",
        "domains": ["salud", "tecnología", "política", "historia", "medio ambiente", "deportes"],
        "max_seeds": 20,
    },
    "jojajovai.jsonl": {
        "description": "Jojajovai — periodismo paraguayo, noticias",
        "domains": ["política", "economía", "salud", "educación", "deportes", "cultura"],
        "max_seeds": 20,
    },
}

SEEDS_DIR = "seeds"


def cargar_seeds(path: str, campo: str = "text", max_seeds: int = 25) -> list[str]:
    """Carga oraciones seed desde un archivo JSONL, muestreando hasta max_seeds."""
    seeds = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if campo in obj and obj[campo]:
                seeds.append(obj[campo])
    if len(seeds) > max_seeds:
        seeds = random.sample(seeds, max_seeds)
    return seeds


def elegir_seed_file() -> str:
    """Menú interactivo para seleccionar el archivo seed."""
    archivos_disponibles = [
        f for f in SEED_CATALOG
        if os.path.exists(os.path.join(SEEDS_DIR, f))
    ]

    if not archivos_disponibles:
        print("[Error] No se encontraron archivos seed en la carpeta 'seeds/'.")
        sys.exit(1)

    print("\n=== Selecciona el archivo seed ===")
    for i, fname in enumerate(archivos_disponibles, 1):
        desc = SEED_CATALOG[fname]["description"]
        print(f"  [{i}] {fname}  —  {desc}")

    while True:
        try:
            opcion = input(f"\nElegí un número (1-{len(archivos_disponibles)}): ").strip()
            idx = int(opcion) - 1
            if 0 <= idx < len(archivos_disponibles):
                return archivos_disponibles[idx]
            else:
                print(f"  Ingresá un número entre 1 y {len(archivos_disponibles)}.")
        except (ValueError, KeyboardInterrupt):
            print("\nCancelado.")
            sys.exit(0)


# ─────────────────────────────────────────────────────────────
# Modo loop continuo (--loop): round-robin sobre todas las seeds
# disponibles, con pausa entre vueltas, sin selector interactivo.
# ─────────────────────────────────────────────────────────────
def ejecutar_loop_continuo(duracion_minutos: float | None = None, pausa_segundos: int = 5,
                             por_dominio: int = 10) -> None:
    """Recorre round-robin las seeds disponibles en seeds/, generando
    Estrategia 5 para cada una, con una pausa entre vueltas.

    Si se pasa duracion_minutos, el loop corta al TERMINAR la vuelta en la
    que se cumple el tiempo (nunca a mitad de una generación). Sin ese
    parámetro, corre indefinidamente hasta que se lo interrumpa (Ctrl+C).
    """
    archivos_disponibles = [
        f for f in SEED_CATALOG
        if os.path.exists(os.path.join(SEEDS_DIR, f))
    ]
    if not archivos_disponibles:
        print("[Error] No se encontraron archivos seed en la carpeta 'seeds/'.")
        sys.exit(1)

    print(f"=== Estrategia 5 — Modo loop continuo (round-robin sobre {len(archivos_disponibles)} seed(s)) ===")
    if duracion_minutos is not None:
        print(f"[Info] Se detiene al terminar la vuelta en la que se cumplan {duracion_minutos} minuto(s).")
    else:
        print("[Info] Sin ventana de tiempo — cortar manualmente con Ctrl+C.")

    hora_limite = time.monotonic() + duracion_minutos * 60 if duracion_minutos is not None else None
    vuelta = 0

    try:
        while True:
            for seed_filename in archivos_disponibles:
                vuelta += 1
                seed_path = os.path.join(SEEDS_DIR, seed_filename)
                domains = SEED_CATALOG[seed_filename]["domains"]
                max_seeds = SEED_CATALOG[seed_filename]["max_seeds"]

                print(f"\n--- Vuelta {vuelta}: {seed_filename} ---")
                seed_sentences = cargar_seeds(seed_path, max_seeds=max_seeds)
                print(f"[Info] {len(seed_sentences)} seeds cargadas | dominios: {', '.join(domains)}")

                ruta, _ = generar_estrategia_5(
                    ejemplos_few_shot=seed_sentences,
                    dominios=domains,
                    por_dominio=por_dominio,
                    seed_file_name=seed_filename,
                )
                print(f"=== Vuelta {vuelta} completada. Archivo: {ruta} ===")

                if hora_limite is not None and time.monotonic() >= hora_limite:
                    print(f"\n[Info] Ventana de tiempo cumplida al terminar la vuelta {vuelta}. Deteniendo.")
                    return

                print(f"[Info] Pausa de {pausa_segundos}s antes de la próxima vuelta...")
                time.sleep(pausa_segundos)
    except KeyboardInterrupt:
        print(f"\n[Info] Interrumpido manualmente después de {vuelta} vuelta(s).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Estrategia 5 — Generación few-shot con LLM")
    parser.add_argument(
        "--loop", action="store_true",
        help="Modo continuo: recorre round-robin todas las seeds disponibles, con "
             "pausa entre vueltas, en vez de pedir una sola seed por selector interactivo.",
    )
    parser.add_argument(
        "--duracion-minutos", type=float, default=None,
        help="(solo con --loop) Corta el loop al terminar la vuelta en la que se cumpla "
             "este tiempo. Sin este flag, corre indefinidamente hasta Ctrl+C.",
    )
    parser.add_argument(
        "--pausa-segundos", type=int, default=5,
        help="(solo con --loop) Pausa entre vueltas del loop (default: 5s).",
    )
    parser.add_argument(
        "--por-dominio", type=int, default=10,
        help="Frases a generar por dominio en cada vuelta (default: 10).",
    )
    args = parser.parse_args()

    if args.loop:
        ejecutar_loop_continuo(
            duracion_minutos=args.duracion_minutos,
            pausa_segundos=args.pausa_segundos,
            por_dominio=args.por_dominio,
        )
    else:
        print("=== Estrategia 5 — Generación few-shot con LLM ===")

        seed_filename = elegir_seed_file()
        seed_path = os.path.join(SEEDS_DIR, seed_filename)

        # Obtener dominios del catálogo (los del corpus elegido)
        domains = SEED_CATALOG[seed_filename]["domains"]

        print(f"\n[Info] Seed seleccionado : {seed_filename}")
        print(f"[Info] Dominios a generar: {', '.join(domains)}")

        seed_sentences = cargar_seeds(seed_path, max_seeds=SEED_CATALOG[seed_filename]["max_seeds"])
        print(f"[Info] {len(seed_sentences)} seeds cargadas")

        print("\n=== Iniciando generación... ===")
        ruta, prompts = generar_estrategia_5(
            ejemplos_few_shot=seed_sentences,
            dominios=domains,
            por_dominio=args.por_dominio,
            seed_file_name=seed_filename,
        )
        print(f"=== Completado. Archivo guardado en: {ruta} ===")
