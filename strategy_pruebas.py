"""
SCRIPTS DEL LEAD DEV — Estrategias 3 y 5
==========================================
Esto es lo que el Lead Dev corre para generar. La salida queda en
raw/estrategia3/ o raw/estrategia5/, según corresponda.

Requisitos: pip install google-genai python-dotenv --break-system-packages
Necesita: .env con GEMINI_API_KEY
"""

import os
import json
import random
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

CARPETA_RAW = "raw"
MAX_REINTENTOS = 3
ESPERA_ENTRE_REINTENTOS = 5  # segundos, se duplica en cada intento


def guardar_lote(registros: list[dict], estrategia: str) -> str:
    """Guarda el lote generado en raw/estrategia{N}/, separado por estrategia."""
    carpeta = os.path.join(CARPETA_RAW, f"estrategia{estrategia}")
    os.makedirs(carpeta, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    ruta = os.path.join(carpeta, f"lote_{timestamp}.jsonl")
    with open(ruta, "w", encoding="utf-8") as f:
        for reg in registros:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")
    print(f"[Lead Dev] Lote guardado: {ruta} ({len(registros)} registros)")
    return ruta


def llamar_gemini_con_reintentos(client, prompt: str):
    """
    Reintenta hasta MAX_REINTENTOS veces si la API falla (500, timeouts, etc.),
    con espera creciente entre intentos. Si todos fallan, devuelve None
    en vez de tirar la excepción y perder el lote entero.
    """
    espera = ESPERA_ENTRE_REINTENTOS
    for intento in range(1, MAX_REINTENTOS + 1):
        try:
            response = client.models.generate_content(
                model="gemini-3.5-flash",
                contents=prompt,
            )
            return response.text.strip()
        except Exception as e:
            print(f"    ⚠️  Intento {intento}/{MAX_REINTENTOS} falló: {e}")
            if intento < MAX_REINTENTOS:
                print(f"    Esperando {espera}s antes de reintentar...")
                time.sleep(espera)
                espera *= 2  # backoff exponencial
    print("    🚨 Se agotaron los reintentos — se omite esta oración.")
    return None


# ─────────────────────────────────────────────────────────────
# ESTRATEGIA 3 — Transformaciones controladas
# ─────────────────────────────────────────────────────────────
def transformar_oracion(oracion_base: str, client, tipo_cambio: str = "sinonimo") -> str:
    """
    Usa el LLM para hacer UN cambio puntual y acotado sobre la oración,
    no una generación libre. tipo_cambio: "sinonimo" o "reordenar".
    """
    if tipo_cambio == "sinonimo":
        instruccion = (
            "Reescribí esta oración en guaraní cambiando SOLO una palabra "
            "por un sinónimo o palabra relacionada. No cambies nada más, "
            "no agregues ni quites palabras. Devolvé solo la oración resultante."
        )
    else:  # reordenar
        instruccion = (
            "Reescribí esta oración en guaraní moviendo UN fragmento de lugar "
            "(por ejemplo, el orden de una frase adverbial), sin cambiar el "
            "significado ni agregar/quitar palabras. Devolvé solo la oración resultante."
        )

    prompt = f"{instruccion}\n\nOración: {oracion_base}"
    return llamar_gemini_con_reintentos(client, prompt)


def generar_estrategia_3(oraciones_semilla: list[dict], variantes_por_semilla: int = 3):
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        raise ValueError("Falta GEMINI_API_KEY o API_KEY en el .env")
    client = genai.Client(api_key=api_key)

    tipos = ["sinonimo", "reordenar"]
    registros = []
    fallidas = 0
    for semilla in oraciones_semilla:
        for i in range(variantes_por_semilla):
            tipo = tipos[i % len(tipos)]  # alterna entre sinónimo y reordenar
            variante = transformar_oracion(semilla["texto"], client, tipo_cambio=tipo)
            if variante is None:
                fallidas += 1
                continue  # se omite, pero el lote sigue con las demás
            registros.append({
                "texto": variante,
                "texto_base": semilla["texto"],
                "tipo_transformacion": tipo,
                "dominio": semilla.get("dominio", "sin_clasificar"),
                "estrategia": "3",
            })
    if fallidas > 0:
        print(f"⚠️  {fallidas} oraciones fallaron incluso con reintentos y se omitieron.")
    return guardar_lote(registros, estrategia="3")


# ─────────────────────────────────────────────────────────────
# ESTRATEGIA 5 — Generación few-shot con LLM
# ─────────────────────────────────────────────────────────────
def armar_prompt(ejemplos: list[str], dominio: str) -> str:
    ejemplos_texto = "\n".join(f"- {e}" for e in ejemplos)
    return (
        f"Sos un hablante nativo de guaraní paraguayo. Generá 1 frase nueva, "
        f"natural (no traducción literal del español), en el dominio: {dominio}.\n\n"
        f"Ejemplos del estilo esperado:\n{ejemplos_texto}\n\n"
        f"Devolvé solo la frase nueva, sin explicaciones."
    )


def generar_estrategia_5(ejemplos_few_shot: list[str], dominios: list[str], por_dominio: int = 10, seed_file_name: str = "") -> tuple[str, list[str]]:
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        raise ValueError("Falta GEMINI_API_KEY o API_KEY en el .env")
    client = genai.Client(api_key=api_key)

    registros = []
    prompts = []
    for dominio in dominios:
        for _ in range(por_dominio):
            prompt = armar_prompt(ejemplos_few_shot, dominio)
            response = client.models.generate_content(
                model="gemini-3.5-flash",
                contents=prompt,
            )
            texto_generado = response.text.strip()
            registros.append({
                "texto": texto_generado,
                "dominio": dominio,
                "estrategia": "5",
                "prompt": prompt,
                "seed_file": seed_file_name,
            })
            prompts.append(prompt)
    ruta = guardar_lote(registros, estrategia="5")
    return ruta, prompts


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    semillas = [
        {"texto": "Jagua ho'úta so'o ko'ẽrõ", "dominio": "vida_cotidiana"},
        {"texto": "Aguyje ndéve g̃uarã che irũ", "dominio": "agradecimiento"},
    ]

    print("=== [Lead Dev] Generando Estrategia 3 ===")
    generar_estrategia_3(semillas, variantes_por_semilla=3)

    print("\n=== [Lead Dev] Generando Estrategia 5 ===")
    generar_estrategia_5(
        ejemplos_few_shot=[s["texto"] for s in semillas],
        dominios=["salud", "educación"],
        por_dominio=5,
    )