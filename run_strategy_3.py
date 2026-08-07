import os
from dotenv import load_dotenv

load_dotenv()

# Import the strategy function for Strategy 3
from strategy_gemini_dev import generar_estrategia_3

# Seed sentences (same as used in the main script)
semillas = [
    {"texto": "Jagua ho'úta so'o ko'ẽrõ", "dominio": "vida_cotidiana"},
    {"texto": "Aguyje ndéve g̃uarã che irũ", "dominio": "agradecimiento"},
]

if __name__ == "__main__":
    print("=== Ejecutando Estrategia 3 ===")
    generar_estrategia_3(semillas, variantes_por_semilla=3)
    print("=== Estrategia 3 completada ===")
