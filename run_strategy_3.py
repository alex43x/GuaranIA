#!/usr/bin/env python3
"""run_strategy_3.py
====================================================
Genera Estrategia 3 — SOLO reordenación (el sinónimo ahora va por
diccionario_estrategia3.py, aparte). Tomando como base lo que YA
generó la Estrategia 5.

Máximo 4 reordenaciones por oración — nunca más, aunque haya cupo:
generar_estrategia_3() se detiene sola si dos intentos seguidos no
dan una variante realmente nueva (no infla el número inventando).
"""

import os
import json
import glob
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

# Cambiá a True una vez que el Data Wrangler haya validado el lote de
# la Estrategia 5 — ahí sí conviene usar lo aprobado, no lo crudo.
ESTRATEGIA_5_VALIDADA = False

# Límite duro — regla de negocio, no un objetivo a alcanzar como fuera.
MAX_REORDENACIONES = 4

# ── MODO PRUEBA ──
MODO_PRUEBA = True
LIMITE_PRUEBA = 3


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
    print("=== Ejecutando Estrategia 3 — SOLO reordenación (a partir de Estrategia 5) ===")

    if not ESTRATEGIA_5_VALIDADA:
        print("⚠️  Usando datos CRUDOS de la Estrategia 5 (todavía sin validar).")
        print("    Tratá este lote como PRUEBA, no como candidato final.\n")

    semillas = cargar_datos_estrategia_5()
    if not semillas:
        raise RuntimeError("No hay registros utilizables de la Estrategia 5.")

    if MODO_PRUEBA:
        semillas = semillas[:LIMITE_PRUEBA]
        print(f"🧪 MODO PRUEBA: {len(semillas)} semilla(s), hasta {MAX_REORDENACIONES} "
              f"reordenación(es) cada una (máximo {len(semillas) * MAX_REORDENACIONES} llamadas).")
    else:
        print(f"Semillas disponibles: {len(semillas)}. "
              f"Hasta {MAX_REORDENACIONES} reordenación(es) por semilla.")

    output_path = generar_estrategia_3(semillas, max_reordenaciones=MAX_REORDENACIONES)

    with open(output_path, "r", encoding="utf-8") as f:
        lineas_generadas = [ln for ln in f if ln.strip()]

    print(f"\n=== Completado ===")
    print(f"    Semillas: {len(semillas)} | Máximo posible: {len(semillas) * MAX_REORDENACIONES}")
    print(f"    Reordenaciones reales logradas: {len(lineas_generadas)}")
    print(f"    Archivo: {output_path}")
    if MODO_PRUEBA:
        print("    Cuando confirmes que anda bien, poné MODO_PRUEBA = False "
              "y volvé a correr para el lote completo.")