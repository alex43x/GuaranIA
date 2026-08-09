"""
VALIDAR RAWS — Análisis de duplicados en raw/estrategia5/ (solo lectura, sin IA)
===============================================================================
Lee todos los .jsonl de raw/estrategia5/, aplica los filtros locales de
data_wrangler (normalizar_texto + deduplicar_por_texto) y reporta estadísticas
por seed y dominio. No llama a ningún LLM ni API externa, y no modifica nada.

El dedup se paraleliza con mapear_paralelo (workers.py, MAX_WORKERS del .env).

Uso:
    python validar_raws.py
"""

import os
import json
import glob
from collections import defaultdict

from data_wrangler import deduplicar_por_texto
from workers import mapear_paralelo

CARPETA = "raw/estrategia5"


def leer_registros():
    """Lee todos los .jsonl de CARPETA y agrupa los registros por (seed, dominio)."""
    grupos = defaultdict(list)
    archivos = sorted(glob.glob(os.path.join(CARPETA, "**", "*.jsonl"), recursive=True))
    total_lineas = 0

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
                grupos[(seed, dominio)].append({"texto": texto})
                total_lineas += 1

    return grupos, total_lineas


def procesar_grupo(item) -> tuple:
    """Aplica deduplicar_por_texto a un grupo (seed, dominio) -> lista de textos."""
    (seed, dominio), registros = item
    total = len(registros)
    unicos = deduplicar_por_texto(registros)
    descartados = total - len(unicos)
    return (seed, dominio, {"total": total, "descartados": descartados, "ok": len(unicos)})


def validar():
    print("=" * 70)
    print("VALIDACIÓN DE RAWS — SOLO LECTURA (sin IA, filtros locales)")
    print("=" * 70)

    grupos, total = leer_registros()

    print(f"\nAnalizando {total} registros en {len(grupos)} grupos (seed/dominio)...\n")

    contador = {"procesados": 0}
    total_grupos = len(grupos)

    def al_completar(idx, item, resultado):
        contador["procesados"] += 1
        print(f"   Progreso: {contador['procesados']}/{total_grupos} grupos", flush=True)

    resultados = mapear_paralelo(
        list(grupos.items()),
        procesar_grupo,
        on_completado=al_completar,
    )

    print("\n" + "=" * 70)
    print("RESULTADOS POR SEED Y DOMINIO")
    print("=" * 70)

    by_seed = defaultdict(dict)
    for seed, dominio, stats in resultados:
        by_seed[seed][dominio] = stats

    total_descatados = 0

    for seed in sorted(by_seed.keys()):
        print(f"\n--- {seed} ---")
        seed_total = 0
        seed_descartados = 0
        for dominio in sorted(by_seed[seed].keys()):
            s = by_seed[seed][dominio]
            seed_total += s["total"]
            seed_descartados += s["descartados"]
            print(f"  {dominio:<20s} {s['total']:>4d} totales | {s['descartados']:>3d} duplicados | {s['ok']:>3d} ok")
        total_descatados += seed_descartados

    tasa = (total_descatados / total * 100) if total > 0 else 0
    print(f"\n{'=' * 70}")
    print(f"TOTAL: {total} analizados | {total_descatados} duplicados | {total - total_descatados} ok")
    print(f"Tasa de duplicados: {tasa:.1f}%")
    print("=" * 70)


if __name__ == "__main__":
    validar()
