"""
STRATEGY FOR AZURE DEV — Trabaja con Azure OpenAI y datos reales
===================================================================
Este script lee oraciones reales desde 'datos_reales.txt', las procesa
usando Azure OpenAI (GPT-4o-mini por defecto) y genera lotes en raw/.

Requisitos: pip install openai python-dotenv --break-system-packages
Necesita: .env con AZURE_API_KEY
"""

import os
import json
from datetime import datetime
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

CARPETA_RAW = "raw"
ARCHIVO_DATOS = "datos_reales.txt"

# Configuración de Azure OpenAI (modificar según sea necesario)
AZURE_ENDPOINT = "https://guarania-maas.cognitiveservices.azure.com/"
AZURE_MODEL = "gpt-4o-mini"
AZURE_API_VERSION = "2024-12-01-preview"


def guardar_lote(registros: list[dict], estrategia: str) -> str:
    """Guarda el lote generado en raw/."""
    os.makedirs(CARPETA_RAW, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    ruta = os.path.join(CARPETA_RAW, f"estrategia{estrategia}_azure_{timestamp}.jsonl")
    with open(ruta, "w", encoding="utf-8") as f:
        for reg in registros:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")
    print(f"[Azure Dev] Lote guardado: {ruta} ({len(registros)} registros)")
    return ruta


def transformar_oracion(oracion_base: str, client: AzureOpenAI, tipo_cambio: str = "sinonimo") -> str:
    """
    Usa Azure OpenAI para reescribir una oración en Guaraní.
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

    try:
        response = client.chat.completions.create(
            model=AZURE_MODEL,
            messages=[
                {"role": "system", "content": "Sos un experto lingüista y hablante nativo de guaraní paraguayo."},
                {"role": "user", "content": f"{instruccion}\n\nOración: {oracion_base}"}
            ],
            max_tokens=100,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error procesando oración '{oracion_base}': {e}")
        return oracion_base


def procesar_datos_reales(variantes_por_oracion: int = 2):
    api_key = os.getenv("AZURE_API_KEY")
    if not api_key:
        raise ValueError("Falta AZURE_API_KEY en el archivo .env")

    client = AzureOpenAI(
        api_version=AZURE_API_VERSION,
        azure_endpoint=AZURE_ENDPOINT,
        api_key=api_key,
    )

    if not os.path.exists(ARCHIVO_DATOS):
        print(f"[Azure Dev] Creando archivo {ARCHIVO_DATOS} de ejemplo...")
        with open(ARCHIVO_DATOS, "w", encoding="utf-8") as f:
            f.write("Añe'ẽ porãse guaraníme che irũ ndive\n")
            f.write("Mitãkuña oho mbo'ehaópe pyhareve\n")

    with open(ARCHIVO_DATOS, "r", encoding="utf-8") as f:
        oraciones = [line.strip() for line in f if line.strip()]

    print(f"=== [Azure Dev] Cargadas {len(oraciones)} oraciones de {ARCHIVO_DATOS} ===")

    tipos = ["sinonimo", "reordenar"]
    registros = []
    
    for oracion in oraciones:
        for i in range(variantes_por_oracion):
            tipo = tipos[i % len(tipos)]
            print(f"Generando variante '{tipo}' para: {oracion}")
            variante = transformar_oracion(oracion, client, tipo_cambio=tipo)
            registros.append({
                "texto": variante,
                "texto_base": oracion,
                "tipo_transformacion": tipo,
                "dominio": "datos_reales",
                "estrategia": "azure_dev_3",
            })
            
    return guardar_lote(registros, estrategia="3")


if __name__ == "__main__":
    try:
        procesar_datos_reales(variantes_por_oracion=2)
    except Exception as e:
        print(f"Error en la ejecución de Azure Dev: {e}")
