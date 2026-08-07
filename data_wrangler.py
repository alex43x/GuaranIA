"""
DATA WRANGLER — Filtrado y Carga a Google Sheets
=================================================
Este script busca los archivos generados en raw/, los filtra usando
reglas personalizadas y sube los aprobados a Google Sheets.

Requisitos: pip install gspread google-auth python-dotenv --break-system-packages
Necesita: credenciales.json (Cuenta de Servicio de Google Cloud)
"""

import os
import json
import glob
import gspread
from google.oauth2.service_account import Credentials

# Configuración de Google Sheets (modificar según corresponda)
NOMBRE_HOJA = "hackathon-test"
NOMBRE_PESTANA = "para_validar"
CARPETA_RAW = "raw"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def conectar_a_sheets() -> gspread.Worksheet:
    """Autentica con credenciales.json y abre la pestaña correspondiente."""
    ruta_creds = "./credenciales.json"
    if not os.path.exists(ruta_creds):
        raise FileNotFoundError("No se encuentra 'credenciales.json' en la raíz del proyecto.")

    creds = Credentials.from_service_account_file(ruta_creds, scopes=SCOPES)
    cliente = gspread.authorize(creds)
    hoja = cliente.open(NOMBRE_HOJA)
    pestana = hoja.worksheet(NOMBRE_PESTANA)
    return pestana


def filtrar_registros(registros: list[dict]) -> list[dict]:
    """
    Función de marcador para que el Desarrollador de Filtrado escriba su lógica.
    Actualmente es un passthrough (aprueba todo lo que tenga texto no vacío).
    """
    registros_aprobados = []
    for reg in registros:
        texto = reg.get("texto", "").strip()
        
        # --- IMPLEMENTAR FILTROS AQUÍ ---
        # Ejemplo: Evitar textos vacíos o duplicados del texto base
        es_valido = len(texto) > 0 and texto != reg.get("texto_base", "")
        # --------------------------------
        
        if es_valido:
            registros_aprobados.append(reg)
            
    return registros_aprobados


def procesar_y_subir():
    # 1. Conectar a Google Sheets
    print("[Wrangler] Conectando a Google Sheets...")
    try:
        pestana = conectar_a_sheets()
        print("   OK - Conexión establecida.")
    except Exception as e:
        print(f"   ERROR al conectar: {e}")
        return

    # 2. Leer archivos en raw/
    archivos_jsonl = glob.glob(os.path.join(CARPETA_RAW, "*.jsonl"))
    if not archivos_jsonl:
        print(f"[Wrangler] No se encontraron archivos .jsonl en la carpeta '{CARPETA_RAW}'.")
        return

    print(f"[Wrangler] Se encontraron {len(archivos_jsonl)} archivos para procesar.")
    todos_los_registros = []

    for ruta_archivo in archivos_jsonl:
        print(f"   Leyendo {os.path.basename(ruta_archivo)}...")
        with open(ruta_archivo, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    todos_los_registros.append(json.loads(line.strip()))

    print(f"[Wrangler] Registros totales leídos: {len(todos_los_registros)}")

    # 3. Aplicar filtrado
    registros_filtrados = filtrar_registros(todos_los_registros)
    print(f"[Wrangler] Registros aprobados tras filtrado: {len(registros_filtrados)}")

    if not registros_filtrados:
        print("[Wrangler] No hay registros para subir.")
        return

    # 4. Formatear y subir
    # Espera subir columnas como: texto, texto_base, tipo_transformacion, dominio, estrategia
    filas_a_subir = []
    for reg in registros_filtrados:
        filas_a_subir.append([
            reg.get("texto", ""),
            reg.get("texto_base", ""),
            reg.get("tipo_transformacion", ""),
            reg.get("dominio", ""),
            reg.get("estrategia", ""),
        ])

    print(f"[Wrangler] Subiendo {len(filas_a_subir)} filas a '{NOMBRE_HOJA}' -> '{NOMBRE_PESTANA}'...")
    try:
        # Se añaden las filas al final de la hoja existente
        pestana.append_rows(filas_a_subir)
        print("   OK - Carga completada con éxito.")
    except Exception as e:
        print(f"   ERROR al subir los datos: {e}")


if __name__ == "__main__":
    procesar_y_subir()
