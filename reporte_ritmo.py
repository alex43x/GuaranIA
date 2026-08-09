"""
REPORTE DE RITMO — Textos generados por bloque de 30 minutos
============================================================
Lee recursivamente los .jsonl de raw/estrategia3/ y raw/estrategia5/,
extrae el timestamp del nombre del archivo y cuenta cuántos textos
se generaron en cada bloque de 30 minutos.

Secciones:
  1. Por estrategia (e3 vs e5 separado)
  2. Total combinado (e3 + e5)
  3. Desglose por source (subcarpetas como jojajovai, tatoeba/reordenar, etc.)

Uso:
    python reporte_ritmo.py
"""

import os
import re
import json
import glob
from datetime import datetime, timedelta
from collections import defaultdict


CARPETAS = ["raw/estrategia3", "raw/estrategia5"]
PATRON_TIMESTAMP = re.compile(r"lote_(\d{8})_(\d{4,6})\.jsonl$")


def extraer_timestamp(nombre_archivo: str) -> datetime | None:
    m = PATRON_TIMESTAMP.search(nombre_archivo)
    if not m:
        return None
    fecha_str = m.group(1)
    hora_str = m.group(2)
    try:
        if len(hora_str) == 6:
            return datetime.strptime(f"{fecha_str}{hora_str}", "%Y%m%d%H%M%S")
        return datetime.strptime(f"{fecha_str}{hora_str}", "%Y%m%d%H%M")
    except ValueError:
        return None


def redondear_a_bloque(dt: datetime, minutos: int = 30) -> datetime:
    bloque = dt.minute // minutos * minutos
    return dt.replace(minute=bloque, second=0, microsecond=0)


def extraer_source(ruta: str, carpeta_base: str) -> str:
    rel = os.path.relpath(ruta, carpeta_base)
    partes = os.path.normpath(rel).split(os.sep)
    sub = partes[:-1]
    return "/".join(sub) if sub else "(raíz)"


def recolectar():
    """
    Retorna:
        por_estrategia: dict[str, dict[datetime, int]]
        por_source: dict[str, dict[str, dict[datetime, int]]]
    """
    por_estrategia: dict[str, dict[datetime, int]] = {
        "estrategia3": defaultdict(int),
        "estrategia5": defaultdict(int),
    }
    por_source: dict[str, dict[str, dict[datetime, int]]] = {
        "estrategia3": defaultdict(lambda: defaultdict(int)),
        "estrategia5": defaultdict(lambda: defaultdict(int)),
    }

    for carpeta in sorted(CARPETAS):
        estrategia = "estrategia3" if "estrategia3" in carpeta else "estrategia5"
        archivos = sorted(glob.glob(os.path.join(carpeta, "**", "*.jsonl"), recursive=True))

        for ruta in archivos:
            nombre = os.path.basename(ruta)
            dt = extraer_timestamp(nombre)
            if dt is None:
                continue
            bloque = redondear_a_bloque(dt, 30)
            source = extraer_source(ruta, carpeta)

            conteo = 0
            with open(ruta, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        reg = json.loads(line.strip())
                    except json.JSONDecodeError:
                        continue
                    if reg.get("texto", "").strip():
                        conteo += 1

            if conteo > 0:
                por_estrategia[estrategia][bloque] += conteo
                por_source[estrategia][source][bloque] += conteo

    return por_estrategia, por_source


def imprimir_tabla(titulo: str, datos: dict[datetime, int]):
    if not datos:
        print(f"\n  (sin datos)")
        return
    print(f"\n  {'Bloque':<20s} {'Textos':>7s}")
    print(f"  {'-' * 20} {'-' * 7}")
    for bloque in sorted(datos.keys()):
        print(f"  {bloque.strftime('%Y-%m-%d %H:%M'):<20s} {datos[bloque]:>7d}")


def imprimir_tabla_source(titulo: str, datos: dict[str, dict[datetime, int]]):
    if not datos:
        print(f"\n  (sin datos)")
        return

    todas_fechas = sorted(set(
        bloque
        for source_data in datos.values()
        for bloque in source_data.keys()
    ))

    fuentes = sorted(datos.keys())

    header = f"  {'Source':<30s}"
    for fecha in todas_fechas:
        header += f" {fecha.strftime('%m/%d %H:%M'):>14s}"
    header += f" {'TOTAL':>7s}"
    print(f"\n{header}")
    print(f"  {'-' * (30 + len(todas_fechas) * 15 + 7)}")

    totales_por_bloque: dict[datetime, int] = defaultdict(int)

    for fuente in fuentes:
        linea = f"  {fuente:<30s}"
        total_fuente = 0
        for fecha in todas_fechas:
            valor = datos[fuente].get(fecha, 0)
            linea += f" {valor:>14d}"
            total_fuente += valor
            totales_por_bloque[fecha] += valor
        linea += f" {total_fuente:>7d}"
        print(linea)

    linea_total = f"  {'TOTAL':<30s}"
    gran_total = 0
    for fecha in todas_fechas:
        t = totales_por_bloque[fecha]
        linea_total += f" {t:>14d}"
        gran_total += t
    linea_total += f" {gran_total:>7d}"
    print(f"  {'-' * (30 + len(todas_fechas) * 15 + 7)}")
    print(linea_total)


def reportar():
    total_e3 = 0
    total_e5 = 0

    print("=" * 70)
    print("REPORTE DE RITMO — Textos generados por bloque de 30 min")
    print("=" * 70)

    por_estrategia, por_source = recolectar()

    print("\n" + "=" * 70)
    print("SECCIÓN 1 — POR ESTRATEGIA")
    print("=" * 70)

    for estrategia in ["estrategia3", "estrategia5"]:
        datos = por_estrategia[estrategia]
        subtotal = sum(datos.values())
        if estrategia == "estrategia3":
            total_e3 = subtotal
        else:
            total_e5 = subtotal
        print(f"\n  {estrategia.upper()}  (total: {subtotal} textos)")
        imprimir_tabla(estrategia, datos)

    print("\n" + "=" * 70)
    print("SECCIÓN 2 — TOTAL COMBINADO (E3 + E5)")
    print("=" * 70)

    combinado: dict[datetime, int] = defaultdict(int)
    for estrategia in ["estrategia3", "estrategia5"]:
        for bloque, conteo in por_estrategia[estrategia].items():
            combinado[bloque] += conteo

    print(f"\n  Total combinado: {total_e3 + total_e5} textos")
    imprimir_tabla("Combinado", combinado)

    print("\n" + "=" * 70)
    print("SECCIÓN 3 — DESGLOSE POR SOURCE")
    print("=" * 70)

    for estrategia in ["estrategia3", "estrategia5"]:
        datos = por_source[estrategia]
        subtotal = sum(
            sum(source_data.values())
            for source_data in datos.values()
        )
        print(f"\n  {estrategia.upper()}  (total: {subtotal} textos)")
        imprimir_tabla_source(estrategia, datos)

    print()


if __name__ == "__main__":
    reportar()
