#!/usr/bin/env python3
"""run_strategy_3.py
====================================================
Genera Estrategia 3 (transformaciones controladas) tomando como
base lo que YA generó la Estrategia 5 — no el corpus externo original.

CORREGIDO respecto a la versión anterior:
1. Lee de raw/ (o de donde le indiques), filtrando archivos de la
   Estrategia 5, no de seeds/ (que es el corpus externo).
2. variantes_por_semilla se CALCULA para acercarse al total deseado,
   en vez de quedar fijo en 1 (el docstring original lo prometía
   pero el código no lo hacía).
"""

import os
import json
import glob
import math
from dotenv import load_dotenv

load_dotenv()

from strategy_pruebas import generar_estrategia_3

# --------------------------------------------------------------------
# Fuente: lo que generó la Estrategia 5, NO el corpus externo (seeds/).
# Ahora en subcarpetas: raw/estrategia5/ (crudo) o
# procesados/estrategia5/ (ya subido a Sheets), según ESTRATEGIA_5_VALIDADA.
# --------------------------------------------------------------------
RAW_DIR = os.path.join(os.path.dirname(__file__), "raw", "estrategia5")
PROCESADOS_DIR = os.path.join(os.path.dirname(__file__), "procesados", "estrategia5")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "raw", "estrategia3")

# Cambiá a True una vez que el Data Wrangler haya validado el lote de
# la Estrategia 5 — ahí sí conviene usar lo aprobado, no lo crudo.
ESTRATEGIA_5_VALIDADA = False

TOTAL_DESEADO = 100

# ── MODO PRUEBA ──
# Con MODO_PRUEBA=True, solo toma las primeras LIMITE_PRUEBA semillas,
# pero SÍ intenta VARIANTES_PRUEBA variantes de cada una — así ves
# cuántas variaciones reales salen (algunas pueden no tener variación
# posible, ver la nota "sin variación posible" al terminar).
MODO_PRUEBA = True
LIMITE_PRUEBA = 3
VARIANTES_PRUEBA = 3  # intentos por semilla — subilo si querés ver más variedad


def cargar_datos_estrategia_5() -> list[dict]:
    """
    Carga lo generado por la Estrategia 5 — busca en raw/estrategia5/
    (crudo, todavía sin validar) o en procesados/estrategia5/ (ya
    subido a Sheets, según ESTRATEGIA_5_VALIDADA).
    """
    carpeta = PROCESADOS_DIR if ESTRATEGIA_5_VALIDADA else RAW_DIR
    patron = os.path.join(carpeta, "*.jsonl")
    archivos = glob.glob(patron)

    if not archivos:
        raise RuntimeError(
            f"No se encontraron archivos .jsonl en '{carpeta}'. "
            f"¿Ya corriste generar_estrategia_5()? ¿Están en la carpeta correcta?"
        )

    registros = []
    for path in archivos:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if "texto" in record and "dominio" in record:
                        registros.append({"texto": record["texto"], "dominio": record["dominio"]})
                except json.JSONDecodeError:
                    continue

    print(f"Leídos {len(registros)} registros de {len(archivos)} archivo(s) de Estrategia 5 "
          f"({'validados' if ESTRATEGIA_5_VALIDADA else 'CRUDOS, sin validar'}).")
    return registros


if __name__ == "__main__":
    print("=== Ejecutando Estrategia 3 (a partir de Estrategia 5) ===")

    if not ESTRATEGIA_5_VALIDADA:
        print("⚠️  Usando datos CRUDOS de la Estrategia 5 (todavía sin validar).")
        print("    Cualquier error de la Estrategia 5 se va a duplicar acá.")
        print("    Tratá este lote como PRUEBA, no como candidato final.\n")

    semillas = cargar_datos_estrategia_5()
    if not semillas:
        raise RuntimeError("No hay registros utilizables de la Estrategia 5.")

    if MODO_PRUEBA:
        semillas = semillas[:LIMITE_PRUEBA]
        variantes_por_semilla = VARIANTES_PRUEBA
        total_intentos = len(semillas) * variantes_por_semilla
        print(f"🧪 MODO PRUEBA: {len(semillas)} semilla(s), hasta {variantes_por_semilla} "
              f"variante(s) cada una ({total_intentos} llamadas a Gemini como máximo).")
    else:
        # Calcular variantes por semilla para acercarse al total deseado
        variantes_por_semilla = max(1, math.ceil(TOTAL_DESEADO / len(semillas)))
        print(f"Semillas disponibles: {len(semillas)}. "
              f"Generando {variantes_por_semilla} variante(s) por semilla "
              f"(objetivo: ~{TOTAL_DESEADO} registros).")

    output_path = generar_estrategia_3(semillas, variantes_por_semilla=variantes_por_semilla)

    if MODO_PRUEBA:
        with open(output_path, "r", encoding="utf-8") as f:
            lineas_generadas = [ln for ln in f if ln.strip()]
        print(f"=== Prueba completada ===")
        print(f"    Intentos:  {total_intentos} (máximo posible)")
        print(f"    Logradas:  {len(lineas_generadas)} variantes reales")
        print(f"    Revisá el detalle en: {output_path}")
        print("    Cuando confirmes que anda bien, poné MODO_PRUEBA = False "
              "y volvé a correr para el lote completo.")
    else:
        # Truncar solo si nos pasamos del objetivo
        with open(output_path, "r", encoding="utf-8") as f:
            lineas = [ln for ln in f if ln.strip()]

        if len(lineas) > TOTAL_DESEADO:
            ruta_truncada = output_path.replace(".jsonl", f"_{TOTAL_DESEADO}.jsonl")
            with open(ruta_truncada, "w", encoding="utf-8") as f:
                f.writelines(lineas[:TOTAL_DESEADO])
            print(f"Truncado a {TOTAL_DESEADO} registros -> {ruta_truncada}")
        else:
            print(f"Generados {len(lineas)} registros (objetivo ~{TOTAL_DESEADO}).")

    print("=== Estrategia 3 completada ===")