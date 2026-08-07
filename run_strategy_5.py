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

# Path to the seed file
SEED_FILE = os.path.join("seeds", "belele.jsonl")

# Load seed sentences from the JSONL file
def cargar_seeds(path: str, campo: str = "text", max_seeds: int = 10) -> list[str]:
    """Load seed sentences from a JSONL file, sampling up to max_seeds."""
    seeds = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if campo in obj and obj[campo]:
                seeds.append(obj[campo])
    # Sample a subset to keep the few-shot prompt manageable
    if len(seeds) > max_seeds:
        seeds = random.sample(seeds, max_seeds)
    return seeds

# Domains for which we want to generate sentences
domains = ["salud", "educación"]

if __name__ == "__main__":
    print("=== Ejecutando Estrategia 5 ===")
    seed_sentences = cargar_seeds(SEED_FILE)
    print(f"[Info] {len(seed_sentences)} seeds cargadas desde {SEED_FILE}")
    ruta, prompts = generar_estrategia_5(
        ejemplos_few_shot=seed_sentences,
        dominios=domains,
        por_dominio=5,
    )
    print("=== Estrategia 5 completada ===")
