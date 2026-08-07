import os
import sys
from dotenv import load_dotenv
import json
from datetime import datetime

# Ensure UTF-8 output on Windows console
sys.stdout.reconfigure(encoding='utf-8')

# Load environment variables (GEMINI_API_KEY, etc.)
load_dotenv()

# Import the strategy function from the main module
from strategy_gemini_dev import generar_estrategia_5

# Few‑shot seed sentences – same as those used by the main script
seed_sentences = [
    "Jagua ho'úta so'o ko'ẽrõ",
    "Aguyje ndéve g̃uarã che irũ",
]

# Domains for which we want to generate sentences
domains = ["salud", "educación"]

if __name__ == "__main__":
    print("=== Ejecutando Estrategia 5 ===")
    ruta, prompts = generar_estrategia_5(
        ejemplos_few_shot=seed_sentences,
        dominios=domains,
        por_dominio=5,
    )
    print("=== Estrategia 5 completada ===")

