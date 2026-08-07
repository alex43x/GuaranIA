#!/usr/bin/env python3
"""run_strategy_3.py
====================================================
Standalone script to execute **Estrategia 3** (controlled
sentence transformations) using the Gemini‑based implementation
found in `strategy_gemini_dev.py`.

This version reads **all seed files** from the `seeds/` folder
(JSONL, each line with `"texto"` and `"dominio"`). It then
automatically calculates how many variants per seed are needed
to produce **approximately 100 records**. The generated batch is
written to `raw/` with the standard timestamp‑based naming
scheme.
"""

import os
import json
import glob
import random
from dotenv import load_dotenv
import math
# --------------------------------------------------------------------
# Load .env – contains GEMINI_API_KEY or other secrets.
# --------------------------------------------------------------------
load_dotenv()

# --------------------------------------------------------------------
# Import the strategy implementation.
# --------------------------------------------------------------------
from strategy_gemini_dev import generar_estrategia_3

# --------------------------------------------------------------------
# Directory containing seed files (confirmed by the user).
# --------------------------------------------------------------------
SEEDS_DIR = os.path.join(os.path.dirname(__file__), "seeds")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "raw")

def load_seeds() -> list[dict]:
    """Collect all seed records from JSONL files in ``SEEDS_DIR``.

    Each line must be a JSON object with at least the keys
    ``texto`` and ``dominio``. The function returns a flat list of
    dictionaries ready to be passed to ``generar_estrategia_3``.
    """
    seeds = []
    # Find every *.jsonl file in the seeds directory
    seed_files = glob.glob(os.path.join(SEEDS_DIR, "*.jsonl"))
    for path in seed_files:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    # Ensure required keys exist
                    if "texto" in record and "dominio" in record:
                        seeds.append({"texto": record["texto"], "dominio": record["dominio"]})
                except json.JSONDecodeError:
                    # Skip malformed lines but keep processing others
                    continue
    return seeds

if __name__ == "__main__":
    print("=== Ejecutando Estrategia 3 ===")
    all_seeds = load_seeds()
    if not all_seeds:
        raise RuntimeError("No seed records found in the seeds/ directory.")

    # Desired total records per execution
    desired_total = len(all_seeds)
    # Use each seed once to generate one record
    selected_seeds = all_seeds
    variantes_por_semilla = 1
    print(f"Seeds loaded: {len(all_seeds)} – using {len(selected_seeds)} random seed(s) to generate {desired_total} record(s).")

    # Run the strategy with the selected seeds
    output_path = generar_estrategia_3(selected_seeds, variantes_por_semilla=variantes_por_semilla)

    # Ensure exactly desired_total records (truncate if needed)
    if os.path.getsize(output_path) > 0:
        with open(output_path, "r", encoding="utf-8") as f:
            lines = [ln for ln in f.readlines() if ln.strip()]
        if len(lines) > desired_total:
            truncated_path = output_path.replace('.jsonl', f'_{desired_total}.jsonl')
            with open(truncated_path, "w", encoding="utf-8") as f:
                f.writelines(lines[:desired_total])
            print(f"Truncated to {desired_total} records -> {truncated_path}")
        else:
            print(f"Generated {len(lines)} records (<= {desired_total}). No truncation needed.")

    print("=== Estrategia 3 completada ===")
