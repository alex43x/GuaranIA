"""
VALIDAR RAWS — Análisis de errores en raw/estrategia5/ (solo lectura)
======================================================================
Lee todos los .jsonl de raw/estrategia5/, pasa cada texto por el LLM
local y reporta estadísticas por seed y dominio. No modifica nada.

Uso:
    python validar_raws.py
"""

import os
import sys
import json
import glob
import time
from collections import defaultdict

sys.path.insert(0, ".")
from analizador_errores import analizar_oracion, parsear_respuesta, conectar_llm

CARPETA = "raw/estrategia5"
DELAY = 0.5


def validar():
    print("=" * 70)
    print("VALIDACIÓN DE RAWS — SOLO LECTURA")
    print("=" * 70)

    conectar_llm()

    archivos = sorted(glob.glob(os.path.join(CARPETA, "**", "*.jsonl"), recursive=True))
    registros = []

    for ruta in archivos:
        with open(ruta, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    reg = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue
                texto = reg.get("texto", "").strip()
                if not texto:
                    continue
                seed = reg.get("seed_file", "(sin_seed)")
                dominio = reg.get("dominio", "sin_dominio")
                registros.append((seed, dominio, texto))

    total = len(registros)
    print(f"\nAnalizando {total} registros...\n")

    stats = defaultdict(lambda: {"total": 0, "errores": 0})

    for i, (seed, dominio, texto) in enumerate(registros):
        key = (seed, dominio)
        stats[key]["total"] += 1

        try:
            respuesta = analizar_oracion(texto)
            errores = parsear_respuesta(respuesta)
            if errores and errores != "sin errores":
                stats[key]["errores"] += 1
        except Exception as e:
            pass

        if (i + 1) % 20 == 0 or i == total - 1:
            print(f"   Progreso: {i + 1}/{total}")

        time.sleep(DELAY)

    print("\n" + "=" * 70)
    print("RESULTADOS POR SEED Y DOMINIO")
    print("=" * 70)

    total_errores = 0

    by_seed = defaultdict(dict)
    for (seed, dominio), s in stats.items():
        by_seed[seed][dominio] = s

    for seed in sorted(by_seed.keys()):
        print(f"\n--- {seed} ---")
        seed_total = 0
        seed_errores = 0
        for dominio in sorted(by_seed[seed].keys()):
            s = by_seed[seed][dominio]
            seed_total += s["total"]
            seed_errores += s["errores"]
            ok = s["total"] - s["errores"]
            print(f"  {dominio:<20s} {s['total']:>4d} analizados | {s['errores']:>3d} con errores | {ok:>3d} ok")
        total_errores += seed_errores

    tasa = (total_errores / total * 100) if total > 0 else 0
    print(f"\n{'=' * 70}")
    print(f"TOTAL: {total} analizados | {total_errores} con errores | {total - total_errores} ok")
    print(f"Tasa de error: {tasa:.1f}%")
    print("=" * 70)


if __name__ == "__main__":
    validar()
