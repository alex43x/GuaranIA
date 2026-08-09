"""
SCRIPTS DEL LEAD DEV — Estrategias 3 y 5
==========================================
Esto es lo que el Lead Dev corre para generar. La salida queda en raw/,
con el nombre que el Data Wrangler espera para recogerla y filtrarla.

Requisitos: pip install google-genai python-dotenv --break-system-packages
Necesita: .env con GEMINI_API_KEY
"""

import os
import json
import random
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

CARPETA_RAW = "raw"


def guardar_lote(registros: list[dict], estrategia: str, subcarpeta: str | None = None) -> str:
    """Guarda el lote generado en raw/, con el nombre que espera Data Wrangler.
    
    Si 'subcarpeta' se especifica, la ruta será: raw/<subcarpeta>/lote_<timestamp>.jsonl
    En caso contrario: raw/estrategia<N>_lote_<timestamp>.jsonl  (comportamiento original).
    """
    if subcarpeta:
        carpeta = os.path.join(CARPETA_RAW, subcarpeta)
        os.makedirs(carpeta, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ruta = os.path.join(carpeta, f"lote_{timestamp}.jsonl")
    else:
        os.makedirs(CARPETA_RAW, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        ruta = os.path.join(CARPETA_RAW, f"estrategia{estrategia}_lote_{timestamp}.jsonl")
    with open(ruta, "w", encoding="utf-8") as f:
        for reg in registros:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")
    print(f"[Lead Dev] Lote guardado: {ruta} ({len(registros)} registros)")
    return ruta


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
    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt,
    )
    return response.text.strip()


def generar_estrategia_3(oraciones_semilla: list[dict], variantes_por_semilla: int = 3):
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        raise ValueError("Falta GEMINI_API_KEY o API_KEY en el .env")
    client = genai.Client(api_key=api_key)

    tipos = ["sinonimo", "reordenar"]
    registros = []
    for semilla in oraciones_semilla:
        for i in range(variantes_por_semilla):
            tipo = tipos[i % len(tipos)]  # alterna entre sinónimo y reordenar
            variante = transformar_oracion(semilla["texto"], client, tipo_cambio=tipo)
            registros.append({
                "texto": variante,
                "texto_base": semilla["texto"],
                "tipo_transformacion": tipo,
                "dominio": semilla.get("dominio", "sin_clasificar"),
                "estrategia": "3",
            })
    return guardar_lote(registros, estrategia="3")


# ─────────────────────────────────────────────────────────────
# ESTRATEGIA 5 — Generación few-shot con LLM
# ─────────────────────────────────────────────────────────────
def armar_prompt(ejemplos: list[str], dominio: str) -> str:
    ejemplos_texto = "\n".join(f"- {e}" for e in ejemplos)
    return (
        f"Sos un hablante nativo de guaraní paraguayo. Tu tarea es leer las siguientes frases y generar 1 frase nueva "
        f"que esté fuertemente basada en el contenido, tema o estructura de estos ejemplos, pero adaptada o enfocada en el dominio: {dominio}.\n\n"
        f"Frases base:\n{ejemplos_texto}\n\n"
        f"Devolvé solo la frase nueva generada, sin explicaciones ni comillas."
    )


def generar_estrategia_5(ejemplos_few_shot: list[str], dominios: list[str], por_dominio: int = 10, seed_file_name: str = "") -> tuple[str, list[str]]:
    import time
    from google import genai
    from google.genai.errors import ServerError
    from workers import mapear_paralelo

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        raise ValueError("Falta GEMINI_API_KEY o API_KEY en el .env")
    client = genai.Client(api_key=api_key)

    def generar_con_reintentos(prompt: str, max_reintentos: int = 4, espera_inicial: float = 5.0) -> str | None:
        """Llama a la API con reintentos en caso de error 500 transitorio o de
        respuesta sin texto (ej. bloqueada por el filtro de seguridad de Gemini).

        Si se agotan los reintentos, devuelve None en vez de propagar la
        excepción — así una generación fallida no tumba todo el lote (los
        demás items del ThreadPoolExecutor siguen corriendo igual)."""
        for intento in range(1, max_reintentos + 1):
            try:
                response = client.models.generate_content(
                    model="gemini-3.5-flash",
                    contents=prompt,
                )
                if response.text is None:
                    raise ValueError("respuesta vacía de Gemini (posible bloqueo por filtro de seguridad)")
                return response.text.strip()
            except (ServerError, ValueError) as e:
                if intento < max_reintentos:
                    espera = espera_inicial * (2 ** (intento - 1))  # backoff exponencial
                    print(f"  [Reintento {intento}/{max_reintentos - 1}] {e}. Esperando {espera:.0f}s...")
                    time.sleep(espera)
                else:
                    print(f"  [Error] Fallo tras {max_reintentos} intentos: {e}")
                    return None

    # Cada generación es independiente entre sí (no hay dedup que dependa del
    # orden, a diferencia de Estrategia 3), así que se puede aplanar todo en
    # una sola lista de tareas y paralelizarlas sin preservar orden interno.
    tareas = [dominio for dominio in dominios for _ in range(por_dominio)]
    total = len(tareas)

    def procesar_tarea(dominio: str) -> tuple[str, str, str]:
        prompt = armar_prompt(ejemplos_few_shot, dominio)
        texto_generado = generar_con_reintentos(prompt)
        return dominio, prompt, texto_generado

    contador = {"completadas": 0}

    def al_completar(idx, dominio, resultado):
        contador["completadas"] += 1
        _, _, texto_generado = resultado
        estado = "✓" if texto_generado is not None else "✗ (falló tras reintentos)"
        print(f"  [{contador['completadas']}/{total}] dominio={dominio} {estado}", flush=True)

    resultados = mapear_paralelo(tareas, procesar_tarea, on_completado=al_completar)

    registros = []
    prompts = []
    fallidas = 0
    for dominio, prompt, texto_generado in resultados:
        if texto_generado is None:
            fallidas += 1
            continue
        registros.append({
            "texto": texto_generado,
            "dominio": dominio,
            "estrategia": "5",
            "prompt": prompt,
            "seed_file": seed_file_name,
        })
        prompts.append(prompt)

    if fallidas > 0:
        print(f"⚠️  {fallidas} generaciones fallaron incluso con reintentos y se omitieron.")

    seed_stem = os.path.splitext(seed_file_name)[0] if seed_file_name else None
    subcarpeta = f"estrategia5/{seed_stem}" if seed_stem else None
    ruta = guardar_lote(registros, estrategia="5", subcarpeta=subcarpeta)
    return ruta, prompts


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Oraciones semilla de ejemplo (en el evento real: seed set oficial o Jojajovai)
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
