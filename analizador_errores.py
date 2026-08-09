"""
ANALIZADOR DE ERRORES — Detección automática con guarani-llama31-8b (local)
=============================================================================
Lee oraciones del Google Sheet y usa el LLM local fine-tuneado en guaraní
para detectar errores en 6 categorías: acentuación, palabras fusionadas,
conjugación, sintaxis, semántica, y puntuación/símbolos. Escribe el resultado
en la columna "posibles_errores" para revisión manual posterior.

Uso:
    python analizador_errores.py              # Procesa todo el Sheet
    python analizador_errores.py --test       # Prueba el prompt contra feedback/

Requisitos: pip install gspread google-auth requests python-dotenv
Necesita: credenciales.json + conexión a la red HACKATON 2 (192.168.0.59:11434)
"""

import os
import sys
import json
import time
from datetime import datetime

from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
import requests
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

# ─── CONFIGURACIÓN ───
NOMBRE_HOJA = "hackathon-test"
TABS = ["estrategia_3", "estrategia_5"]
COLUMNA_NUEVA = "posibles_errores"
MODELO = "guarani-llama31-8b:latest"
URL_GENERATE = "http://192.168.0.59:11434/api/generate"
DELAY_ENTRE_LLAMADAS = 1.0

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ─── PROMPT ───

PROMPT_ANALISIS = """Sos un experto en guaraní paraguayo. Detectás errores en estas 6 categorías:

1. ACENTUACIÓN/TILDES: tildes nasales faltantes, sobrantes o mal puestas. Ej: "Ho'úta" → "Ho'uta", "g̃uarã" → "guãrã", "amoko" → "amokõ".
2. PALABRAS FUSIONADAS: palabras juntas que deben ir separadas. Ej: "Chepy'ajere" → "Che py'ajere".
3. CONJUGACIÓN VERBAL: persona, número, tiempo o modo incorrectos. Ej: "Ho'u vai chéve" (3ª) en contexto de 1ª persona → "ou vai chéve".
4. SINTAXIS: orden incorrecto, falta de concordancia, calcos del español. Ej: "...rire" como traducción literal de "después de...".
5. SEMÁNTICA: oración sin sentido o contradicciones.
6. PUNTUACIÓN/SÍMBOLOS: signos mal usados, faltantes o sobrantes.

Respondé SIEMPRE en español, describiendo cada error detectado. Si no hay errores, decí "sin errores". Después de tu respuesta, escribí [FIN] y no generes nada más.

Oración: "{texto}"

{{"errores": " """


# ─── CONEXIÓN A SHEETS ───

def conectar_sheets():
    ruta_creds = "credenciales.json"
    if not os.path.exists(ruta_creds):
        raise FileNotFoundError(f"No se encuentra '{ruta_creds}' en la raíz del proyecto.")
    creds = Credentials.from_service_account_file(ruta_creds, scopes=SCOPES)
    cliente = gspread.authorize(creds)
    hoja = cliente.open(NOMBRE_HOJA)
    return hoja


def asegurar_columna(pestana):
    cabecera = pestana.row_values(1)
    if COLUMNA_NUEVA in cabecera:
        return cabecera.index(COLUMNA_NUEVA)
    pestana.update_cell(1, len(cabecera) + 1, COLUMNA_NUEVA)
    print(f"   Columna '{COLUMNA_NUEVA}' agregada a '{pestana.title}'.")
    return len(cabecera)


# ─── CLIENTE LLM LOCAL ───

def conectar_llm():
    try:
        r = requests.get("http://192.168.0.59:11434/api/version", timeout=5)
        r.raise_for_status()
        print(f"[LLM] Conectado: {r.json().get('version', 'ok')}")
    except Exception as e:
        raise ConnectionError(f"No se pudo conectar al servidor LLM (192.168.0.59:11434): {e}")


# ─── ANÁLISIS ───

def analizar_oracion(texto: str) -> str:
    prompt = PROMPT_ANALISIS.format(texto=texto)
    response = requests.post(
        URL_GENERATE,
        json={
            "model": MODELO,
            "prompt": prompt,
            "raw": True,
            "stream": False,
            "stop": ['"}', "\n\n", "Oración:", "[FIN]"],
            "options": {
                "num_predict": 200,
                "temperature": 0.2,
                "top_p": 0.9,
            },
        },
        timeout=60,
    )
    response.raise_for_status()
    completado = response.json()["response"].strip()
    return f'{{"errores": "{completado}'


def parsear_respuesta(respuesta: str) -> str:
    respuesta = respuesta.split("[FIN]")[0].strip()
    try:
        inicio = respuesta.find("{")
        if inicio == -1:
            return respuesta[:200]
        primer_cierre = respuesta.find("}", inicio + 1)
        if primer_cierre != -1:
            candidato = respuesta[inicio:primer_cierre + 1]
        else:
            candidato = respuesta[inicio:] + '"}'
        data = json.loads(candidato)
        errores = data.get("errores", "")
        if errores == "sin errores" or not errores:
            return "sin errores"
        return errores
    except (json.JSONDecodeError, KeyError):
        return respuesta[:200]


# ─── MODO TEST ───

def modo_test():
    print("=" * 60)
    print("MODO TEST: Validando prompt contra feedback/")
    print("=" * 60)

    conectar_llm()

    archivos_feedback = [
        "feedback/estrategia3/para_regenerar.jsonl",
        "feedback/estrategia5/para_regenerar.jsonl",
    ]

    total = 0
    exitos = 0

    for ruta in archivos_feedback:
        if not os.path.exists(ruta):
            print(f"[!] No se encontró: {ruta}")
            continue

        print(f"\n--- {ruta} ---")
        with open(ruta, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.strip():
                    continue
                reg = json.loads(line.strip())
                texto = reg.get("texto", "")
                tipo_error_esperado = reg.get("tipo_error", "")
                if not texto:
                    continue

                total += 1
                print(f"\n[{total}] Oración: {texto}")
                print(f"    Error esperado: {tipo_error_esperado}")

                try:
                    respuesta = analizar_oracion(texto)
                    errores = parsear_respuesta(respuesta)
                    print(f"    Modelo detectó:        {errores}")
                    if errores and errores != "sin errores":
                        exitos += 1
                except Exception as e:
                    print(f"    [!] Error API: {e}")

                time.sleep(DELAY_ENTRE_LLAMADAS)

    print(f"\n{'=' * 60}")
    print(f"RESULTADO TEST: {exitos}/{total} oraciones con errores detectados")
    print("=" * 60)


# ─── MODO SHEET ───

def procesar_sheet(start_row: int = 0):
    print("=" * 60)
    print("ANALIZADOR DE ERRORES — Sheet -> LLM local -> Sheet")
    if start_row:
        print(f"Inicio desde fila: {start_row}")
    print(f"Comienzo: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    hoja = conectar_sheets()
    conectar_llm()

    total_filas = 0
    filas_procesadas = 0
    filas_con_error = 0

    for nombre_tab in TABS:
        try:
            pestana = hoja.worksheet(nombre_tab)
        except gspread.exceptions.WorksheetNotFound:
            print(f"\n[!] Pestaña '{nombre_tab}' no existe, se saltea.")
            continue

        print(f"\n--- Procesando '{nombre_tab}' ---")

        idx_col = asegurar_columna(pestana)
        col_letra = chr(ord("A") + idx_col)

        filas = pestana.get_all_values()
        if len(filas) <= 1:
            print("   Sin datos.")
            continue

        cabecera = [c.strip().lower() for c in filas[0]]
        idx_texto = cabecera.index("texto") if "texto" in cabecera else -1
        if idx_texto == -1:
            print("   [!] No se encontró columna 'texto'.")
            continue

        for i, fila in enumerate(filas[1:], start=2):
            if start_row and i < start_row:
                continue
            if len(fila) <= idx_texto:
                continue

            texto = fila[idx_texto].strip()
            if not texto:
                continue

            ya_analizado = len(fila) > idx_col and fila[idx_col].strip()

            if ya_analizado:
                continue

            total_filas += 1
            print(f"\n   [{total_filas}] Analizando: {texto[:80]}{'...' if len(texto) > 80 else ''}")

            try:
                respuesta = analizar_oracion(texto)
                errores = parsear_respuesta(respuesta)
                print(f"   Resultado: {errores}")

                pestana.update_cell(i, idx_col + 1, errores)
                filas_procesadas += 1

                if errores and errores != "sin errores":
                    filas_con_error += 1
            except Exception as e:
                print(f"   [!] Error: {e}")
                try:
                    pestana.update_cell(i, idx_col + 1, f"ERROR_API: {e}")
                except Exception:
                    pass

            time.sleep(DELAY_ENTRE_LLAMADAS)

    print(f"\n{'=' * 60}")
    print(f"RESUMEN FINAL")
    print(f"   Filas procesadas: {filas_procesadas}")
    print(f"   Errores detectados: {filas_con_error}")
    print(f"   Sin errores: {filas_procesadas - filas_con_error}")
    print(f"   Fin: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)


# ─── MAIN ───

if __name__ == "__main__":
    args = sys.argv[1:]
    if "--test" in args:
        modo_test()
    else:
        start = 0
        for arg in args:
            if arg.startswith("--start="):
                start = int(arg.split("=")[1])
        procesar_sheet(start_row=start)
