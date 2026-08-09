"""
CONTEO DE REGISTROS — Estrategia 3 y 5
=========================================
Agrupa por seed_file y dominio los registros dentro de raw/estrategia3/
y raw/estrategia5/, con la Estrategia 5 separada entre pendientes y
ya procesados por Estrategia 3.

Guarda un informe unificado en conteos/ con timestamp para historial.

Uso:
    python contar_raws.py
"""

import os
import json
import glob
from datetime import datetime
from collections import defaultdict

CARPETA_CONTEOS = "conteos"
CARPETA_E3_RAW = "raw/estrategia3"
CARPETA_E5_RAW = "raw/estrategia5"
CARPETA_E5_PROCESADOS = "raw/estrategia5/procesados_estrategia_3"
CARPETA_E5_PROCESADOS_REORD = os.path.join(CARPETA_E5_PROCESADOS, "reordenar")
CARPETA_E5_PROCESADOS_SIN = os.path.join(CARPETA_E5_PROCESADOS, "sinonimo")


def contar_estrategia(carpeta: str, excluir: list[str] | None = None) -> tuple[dict, int]:
    conteo = defaultdict(lambda: defaultdict(int))

    archivos = sorted(glob.glob(os.path.join(carpeta, "**", "*.jsonl"), recursive=True))
    if excluir:
        archivos = [p for p in archivos if not any(ex in p for ex in excluir)]
    for ruta in archivos:
        with open(ruta, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    reg = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue
                seed = reg.get("seed_file", "(sin_seed)")
                dominio = reg.get("dominio", "sin_dominio")
                conteo[seed][dominio] += 1

    return conteo, len(archivos)


def _formatear_tabla(conteo: dict, nivel: int = 0) -> tuple[str, int]:
    """Formatea una tabla de {seed: {dominio: n}} con indentación."""
    prefix = "  " * nivel
    lineas = []
    total = 0

    for seed in sorted(conteo.keys()):
        dominios = conteo[seed]
        total_seed = sum(dominios.values())
        total += total_seed
        lineas.append(f"{prefix}--- {seed} ---")
        for dominio in sorted(dominios.keys()):
            n = dominios[dominio]
            lineas.append(f"{prefix}  {dominio:<30s} {n:>6d}")
        lineas.append(f"{prefix}  {'Total ' + seed:<30s} {total_seed:>6d}")

    return "\n".join(lineas), total


# ─── ESTRATEGIA 3 ───

def seccion_estrategia_3() -> tuple[str, int]:
    conteo_reord, arch_reord = contar_estrategia(os.path.join(CARPETA_E3_RAW, "**", "reordenar"))
    conteo_sin, arch_sin = contar_estrategia(os.path.join(CARPETA_E3_RAW, "**", "sinonimo"))

    lineas = [
        f"\n*** ESTRATEGIA 3 ***",
        "-" * 70,
        f"Archivos: {arch_reord + arch_sin}",
    ]

    # Reordenar
    lineas.append(f"\n  --- Reordenar ---")
    lineas.append("  " + "-" * 68)
    if conteo_reord:
        tabla, total_reord = _formatear_tabla(conteo_reord, nivel=1)
        lineas.append(tabla)
    else:
        lineas.append("  (ninguno)")
        total_reord = 0
    lineas.append(f"\n  --- {'Total reordenar':<35s} {total_reord:>6d}")

    # Sinónimo
    lineas.append(f"\n  --- Sinónimo ---")
    lineas.append("  " + "-" * 68)
    if conteo_sin:
        tabla, total_sin = _formatear_tabla(conteo_sin, nivel=1)
        lineas.append(tabla)
    else:
        lineas.append("  (ninguno)")
        total_sin = 0
    lineas.append(f"\n  --- {'Total sinónimo':<35s} {total_sin:>6d}")

    total = total_reord + total_sin
    lineas.append(f"\n  {'Total ESTRATEGIA 3':<30s} {total:>6d}")
    return "\n".join(lineas), total


# ─── ESTRATEGIA 5 ───

def seccion_estrategia_5() -> tuple[str, int]:
    conteo_pend, arch_pend = contar_estrategia(CARPETA_E5_RAW, excluir=["procesados_estrategia_3"])
    conteo_reord, arch_reord = contar_estrategia(CARPETA_E5_PROCESADOS_REORD)
    conteo_sin, arch_sin = contar_estrategia(CARPETA_E5_PROCESADOS_SIN)
    arch_proc = arch_reord + arch_sin

    lineas = [
        f"\n*** ESTRATEGIA 5 ***",
        "-" * 70,
        f"Archivos pendientes: {arch_pend}  |  Procesados por E3: {arch_proc}",
    ]

    # Pendientes
    lineas.append(f"\n  --- Pendientes ---")
    lineas.append("  " + "-" * 68)
    if conteo_pend:
        tabla, total_pend = _formatear_tabla(conteo_pend, nivel=1)
        lineas.append(tabla)
    else:
        lineas.append("  (ninguno)")
        total_pend = 0
    lineas.append(f"\n  --- {'Total pendientes':<35s} {total_pend:>6d}")

    # Procesados: reordenar
    lineas.append(f"\n  --- Procesados por Reordenar ---")
    lineas.append("  " + "-" * 68)
    if conteo_reord:
        tabla, total_reord = _formatear_tabla(conteo_reord, nivel=1)
        lineas.append(tabla)
    else:
        lineas.append("  (ninguno)")
        total_reord = 0
    lineas.append(f"\n  --- {'Total reordenar':<35s} {total_reord:>6d}")

    # Procesados: sinónimo
    lineas.append(f"\n  --- Procesados por Sinónimo ---")
    lineas.append("  " + "-" * 68)
    if conteo_sin:
        tabla, total_sin = _formatear_tabla(conteo_sin, nivel=1)
        lineas.append(tabla)
    else:
        lineas.append("  (ninguno)")
        total_sin = 0
    lineas.append(f"\n  --- {'Total sinónimo':<35s} {total_sin:>6d}")

    total_proc = total_reord + total_sin
    total = total_pend + total_proc
    lineas.append(f"\n  {'Total ESTRATEGIA 5':<30s} {total:>6d}")
    return "\n".join(lineas), total


# ─── Main ───

def main():
    os.makedirs(CARPETA_CONTEOS, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    total_general = 0
    secciones = [
        "CONTEO DE REGISTROS",
        "=" * 70,
    ]

    texto3, sub3 = seccion_estrategia_3()
    secciones.append(texto3)
    total_general += sub3

    texto5, sub5 = seccion_estrategia_5()
    secciones.append(texto5)
    total_general += sub5

    secciones.append("\n" + "=" * 70)
    secciones.append(f"{'TOTAL GENERAL':<30s} {total_general:>6d}")
    secciones.append("=" * 70)

    salida = "\n".join(secciones)
    print(salida)

    ruta_txt = os.path.join(CARPETA_CONTEOS, f"conteo_{ts}.txt")
    with open(ruta_txt, "w", encoding="utf-8") as f:
        f.write(salida + "\n")
    print(f"\nGuardado en: {ruta_txt}")


if __name__ == "__main__":
    main()
