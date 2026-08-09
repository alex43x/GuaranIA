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
import threading
import time
from datetime import datetime
from dotenv import load_dotenv

from workers import mapear_paralelo

load_dotenv()

CARPETA_RAW = "raw"
MAX_REINTENTOS = 3
ESPERA_ENTRE_REINTENTOS = 5  # segundos, se duplica en cada intento
TIMEOUT_GEMINI_MS = 60_000  # si una llamada se cuelga más de esto, falla y se reintenta


def guardar_lote(registros: list[dict], estrategia: str, subcarpeta: str | None = None) -> str:
    """Guarda el lote generado en raw/, con el nombre que espera Data Wrangler.

    Si 'subcarpeta' se especifica, la ruta será: raw/<subcarpeta>/lote_<timestamp>.jsonl
    En caso contrario: raw/estrategia{N}/lote_<timestamp>.jsonl (comportamiento original).
    """
    if subcarpeta:
        carpeta = os.path.join(CARPETA_RAW, subcarpeta)
        os.makedirs(carpeta, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ruta = os.path.join(carpeta, f"lote_{timestamp}.jsonl")
    else:
        carpeta = os.path.join(CARPETA_RAW, f"estrategia{estrategia}")
        os.makedirs(carpeta, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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
def _normalizar_para_comparar(texto: str) -> str:
    """Normaliza para detectar 'sin cambio real' aunque varíe mayúsculas/espacios/puntuación."""
    import re
    t = texto.lower().strip()
    t = re.sub(r"[.,;:!?¡¿'\"]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t


def transformar_oracion(oracion_base: str, client, tipo_cambio: str = "sinonimo") -> str | None:
    """
    Usa el LLM para hacer UN cambio puntual y acotado sobre la oración,
    no una generación libre. tipo_cambio: "sinonimo" o "reordenar".

    Devuelve None si:
    - la oración es demasiado corta para "reordenar" (< 3 palabras), o
    - Gemini devolvió la oración prácticamente sin cambios (no encontró
      una variación válida) — esto se detecta, no se guarda como si
      fuera una variante real.
    """
    n_palabras = len(oracion_base.split())

    if tipo_cambio == "reordenar" and n_palabras < 3:
        print(f"    Oración muy corta ({n_palabras} palabras) para reordenar, se omite este tipo.")
        return None

    if tipo_cambio == "sinonimo":
        instruccion = (
            "Reescribí esta oración en guaraní cambiando lo que realmente pueda "
            "reemplazarse por un sinónimo o expresión equivalente — puede ser una "
            "sola palabra, o una expresión corta si esa es la unidad de significado "
            "real (por ejemplo, una locución que funciona como una sola idea). "
            "No cambies nada que no tenga un sinónimo razonable, no agregues ni "
            "quites contenido que no sea parte del reemplazo. Devolvé solo la "
            "oración resultante. Si la oración es tan corta que no hay nada con "
            "sinónimo razonable, respondé exactamente: SIN_VARIACION_POSIBLE"
        )
    else:  # reordenar
        instruccion = (
            "Reescribí esta oración en guaraní moviendo el fragmento que realmente "
            "admita reordenarse sin romper el significado (por ejemplo, una frase "
            "adverbial, un complemento, o el orden de una cláusula) — el tamaño de "
            "ese fragmento depende de la oración, no tiene que ser una sola palabra. "
            "No agregues ni quites palabras, solo cambiá el orden. Devolvé solo la "
            "oración resultante. Si la oración es tan corta o simple que no hay "
            "ningún reordenamiento razonable, respondé exactamente: SIN_VARIACION_POSIBLE"
        )

    prompt = f"{instruccion}\n\nOración: {oracion_base}"
    resultado = llamar_gemini_con_reintentos(client, prompt)

    if resultado is None:
        return None

    if "SIN_VARIACION_POSIBLE" in resultado:
        print(f"    Gemini indicó que no hay variación posible para: \"{oracion_base}\"")
        return None

    if _normalizar_para_comparar(resultado) == _normalizar_para_comparar(oracion_base):
        print(f"    ⚠️  La 'variante' salió idéntica a la original, se descarta: \"{oracion_base}\"")
        return None

    return resultado


def generar_estrategia_3(oraciones_semilla: list[dict], max_reordenaciones: int = 4):
    """
    SOLO reordenación (el sinónimo ahora lo maneja el diccionario, en
    diccionario_estrategia3.py). Intenta hasta max_reordenaciones
    variantes distintas por oración — se detiene antes si dos intentos
    seguidos no dan nada nuevo (sin inventar variantes que no existen).

    Escribe cada variante a disco (append + flush) apenas se genera, en vez
    de acumular todo en memoria y guardar recién al final — así, si el
    proceso se cuelga y hay que matarlo, lo ya generado no se pierde. Cada
    llamada a Gemini además tiene un timeout de TIMEOUT_GEMINI_MS: si la
    red se cuelga a mitad de un request, ese intento falla solo y se
    reintenta (con backoff) en vez de bloquear el hilo para siempre.
    """
    from google import genai
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        raise ValueError("Falta GEMINI_API_KEY o API_KEY en el .env")
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=TIMEOUT_GEMINI_MS))

    # ── Escritura incremental ───────────────────────────────────
    # El archivo de destino se decide por seed_file, que ya se conoce ANTES
    # de generar nada (no depende de la respuesta de Gemini): se abre la
    # primera vez que hace falta y se escribe cada variante apenas se
    # produce, sin esperar a que termine todo el lote. Un solo lock global
    # protege apertura + escritura (el costo es despreciable frente a la
    # latencia de red de cada llamada a Gemini).
    lock_escritura = threading.Lock()
    archivos_abiertos: dict[str, object] = {}
    rutas_por_seed: dict[str, str] = {}
    conteo_por_seed: dict[str, int] = {}

    def escribir_registro(registro: dict) -> None:
        seed_file = registro.get("seed_file", "")
        with lock_escritura:
            if seed_file not in archivos_abiertos:
                if seed_file:
                    seed_stem = os.path.splitext(os.path.basename(seed_file))[0]
                    carpeta = os.path.join(CARPETA_RAW, "estrategia3", seed_stem, "reordenar")
                else:
                    carpeta = os.path.join(CARPETA_RAW, "estrategia3")
                os.makedirs(carpeta, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                ruta = os.path.join(carpeta, f"lote_{timestamp}.jsonl")
                archivos_abiertos[seed_file] = open(ruta, "w", encoding="utf-8")
                rutas_por_seed[seed_file] = ruta
                conteo_por_seed[seed_file] = 0
            f = archivos_abiertos[seed_file]
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
            f.flush()
            conteo_por_seed[seed_file] += 1

    def procesar_semilla(semilla: dict) -> tuple[int, int]:
        """Corre las hasta max_reordenaciones variantes de UNA semilla, en orden
        (la lógica de dedup/corte temprano depende de ese orden). Lo que
        mapear_paralelo() paraleliza es esto corriendo para varias semillas
        a la vez, no las variantes dentro de una misma semilla."""
        variantes_vistas = []
        intentos_sin_exito_seguidos = 0
        seed_file = semilla.get("seed_file", "")
        n_generadas = 0
        sin_variacion_semilla = 0

        preview = semilla["texto"][:50] + ("..." if len(semilla["texto"]) > 50 else "")
        print(f"  → arrancando: \"{preview}\"", flush=True)

        for _ in range(max_reordenaciones):
            variante = transformar_oracion(semilla["texto"], client, tipo_cambio="reordenar")

            if variante is None:
                sin_variacion_semilla += 1
                intentos_sin_exito_seguidos += 1
                if intentos_sin_exito_seguidos >= 2:
                    break
                continue

            clave = _normalizar_para_comparar(variante)
            if clave in variantes_vistas:
                intentos_sin_exito_seguidos += 1
                if intentos_sin_exito_seguidos >= 2:
                    break
                continue

            variantes_vistas.append(clave)
            intentos_sin_exito_seguidos = 0
            escribir_registro({
                "texto": variante,
                "texto_base": semilla["texto"],
                "tipo_transformacion": "reordenar",
                "dominio": semilla.get("dominio", "sin_clasificar"),
                "estrategia": "3",
                "seed_file": seed_file,
            })
            n_generadas += 1

        return n_generadas, sin_variacion_semilla

    total = len(oraciones_semilla)
    completadas = 0
    sin_variacion = 0

    def al_completar(idx, semilla, resultado):
        nonlocal completadas
        completadas += 1
        n_generadas, _ = resultado
        seed_file = semilla.get("seed_file", "")
        seed_tag = os.path.splitext(os.path.basename(seed_file))[0] if seed_file else "?"
        preview = semilla["texto"][:50] + ("..." if len(semilla["texto"]) > 50 else "")
        print(f"  [{completadas}/{total}] ({seed_tag}) \"{preview}\" → {n_generadas} variantes", flush=True)

    try:
        resultados = mapear_paralelo(oraciones_semilla, procesar_semilla, on_completado=al_completar)
    finally:
        # Pase lo que pase (éxito, excepción, Ctrl+C) lo ya escrito queda
        # bien cerrado y con el buffer del SO vaciado.
        with lock_escritura:
            for f in archivos_abiertos.values():
                f.close()

    for _, sin_variacion_semilla in resultados:
        sin_variacion += sin_variacion_semilla

    if sin_variacion > 0:
        print(f"ℹ️  {sin_variacion} intentos sin variación posible (oración muy corta, "
              f"o resultado idéntico al original) — no son errores, se omitieron.")

    for seed_file, ruta in rutas_por_seed.items():
        print(f"[Lead Dev] Lote guardado: {ruta} ({conteo_por_seed[seed_file]} registros)")

    return list(rutas_por_seed.values())


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


def generar_estrategia_5(ejemplos_few_shot: list[str], dominios: list[str], por_dominio: int = 10):
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        raise ValueError("Falta GEMINI_API_KEY o API_KEY en el .env")
    client = genai.Client(api_key=api_key)

    # Cada generación es independiente entre sí, así que se aplana todo en
    # una sola lista de tareas y se paraleliza sin preservar orden interno.
    tareas = [dominio for dominio in dominios for _ in range(por_dominio)]
    total = len(tareas)

    def procesar_tarea(dominio: str) -> tuple[str, str, str | None]:
        prompt = armar_prompt(ejemplos_few_shot, dominio)
        texto_generado = llamar_gemini_con_reintentos(client, prompt)
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
        })
        prompts.append(prompt)

    if fallidas > 0:
        print(f"⚠️  {fallidas} generaciones fallaron incluso con reintentos y se omitieron.")
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