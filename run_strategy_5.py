import os
import sys
import json
import random
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


if __name__ == "__main__":
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
        por_dominio=10,
        seed_file_name=seed_filename,
    )
    print(f"=== Completado. Archivo guardado en: {ruta} ===")
