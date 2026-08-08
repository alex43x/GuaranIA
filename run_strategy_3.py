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
# Archivos de E5 ya procesados por E3 se mueven acá para no re-leerlos
PROCESADOS_E3_DIR = os.path.join(os.path.dirname(__file__), "raw", "estrategia5", "procesados_estrategia_3")

# Cambiá a True una vez que el Data Wrangler haya validado el lote de
# la Estrategia 5 — ahí sí conviene usar lo aprobado, no lo crudo.
ESTRATEGIA_5_VALIDADA = False

# Límite duro — regla de negocio, no un objetivo a alcanzar como fuera.
MAX_REORDENACIONES = 4


def listar_seeds_disponibles() -> list[dict]:
    """Escanea raw/estrategia5/ y devuelve info de seeds con archivos pendientes."""
    carpeta = PROCESADOS_DIR if ESTRATEGIA_5_VALIDADA else RAW_DIR
    seeds: dict[str, dict] = {}

    patron = os.path.join(carpeta, "**", "*.jsonl")
    for path in sorted(glob.glob(patron, recursive=True)):
        if "procesados_estrategia_3" in path:
            continue
        seed_dir = os.path.basename(os.path.dirname(path))
        if not seed_dir or seed_dir == os.path.basename(carpeta):
            continue  # archivo suelto en la raíz, no en subcarpeta
        if seed_dir not in seeds:
            seeds[seed_dir] = {"nombre": seed_dir, "archivos": 0, "registros": 0}
        seeds[seed_dir]["archivos"] += 1
        try:
            with open(path, "r", encoding="utf-8") as f:
                seeds[seed_dir]["registros"] += sum(1 for ln in f if ln.strip())
        except Exception:
            pass

    return sorted(seeds.values(), key=lambda s: s["nombre"])


def selector_consola(seeds: list[dict]) -> list[str]:
    """Menú interactivo: el usuario elige seeds por número, coma o 'all'."""
    print("Seeds disponibles en raw/estrategia5/:\n")
    for i, s in enumerate(seeds, 1):
        print(f"  [{i}] {s['nombre']:<20s} {s['archivos']:>3d} archivo(s)  ({s['registros']:>5d} registros pendientes)")
    print()

    while True:
        entrada = input("Elegí (números separados por coma, 'all', o 'q' para salir): ").strip()
        if entrada.lower() in ("q", "quit", "exit"):
            print("Cancelado.")
            exit(0)
        if entrada.lower() == "all":
            return [s["nombre"] for s in seeds]

        elegidas = []
        errores = []
        for parte in entrada.split(","):
            parte = parte.strip()
            if not parte:
                continue
            if "-" in parte:
                try:
                    ini, fin = parte.split("-", 1)
                    for n in range(int(ini), int(fin) + 1):
                        if 1 <= n <= len(seeds):
                            elegidas.append(seeds[n - 1]["nombre"])
                        else:
                            errores.append(str(n))
                except ValueError:
                    errores.append(parte)
            else:
                try:
                    n = int(parte)
                    if 1 <= n <= len(seeds):
                        elegidas.append(seeds[n - 1]["nombre"])
                    else:
                        errores.append(str(n))
                except ValueError:
                    errores.append(parte)

        if errores:
            print(f"  Opciones no válidas: {', '.join(errores)}. Intentá de nuevo.\n")
            continue
        if not elegidas:
            print("  No seleccionaste ninguna seed. Intentá de nuevo.\n")
            continue

        # Deduplicar manteniendo orden
        unicas = []
        for s in elegidas:
            if s not in unicas:
                unicas.append(s)
        print(f"  Seleccionadas: {', '.join(unicas)}\n")
        return unicas


def cargar_datos_estrategia_5(seeds: list[str] | None = None) -> tuple[list[dict], list[str]]:
    """
    Carga lo generado por la Estrategia 5 — busca en raw/estrategia5/
    (crudo, todavía sin validar) o en procesados/estrategia5/ (ya
    subido a Sheets, según ESTRATEGIA_5_VALIDADA).

    Si 'seeds' se especifica, solo se leen archivos de esas subcarpetas.

    Retorna (registros, archivos_leidos). Los archivos dentro de
    procesados_estrategia_3/ se excluyen automáticamente.
    """
    carpeta = PROCESADOS_DIR if ESTRATEGIA_5_VALIDADA else RAW_DIR
    patron = os.path.join(carpeta, "**", "*.jsonl")
    archivos = sorted(glob.glob(patron, recursive=True))

    # Excluir archivos ya procesados por Estrategia 3
    archivos = [p for p in archivos if "procesados_estrategia_3" not in p]

    if seeds:
        archivos = [
            p for p in archivos
            if os.path.basename(os.path.dirname(p)) in seeds
        ]

    if not archivos:
        raise RuntimeError(
            f"No se encontraron archivos .jsonl en '{carpeta}'. "
            f"¿Ya corriste generar_estrategia_5()? ¿Están en la carpeta correcta?"
        )

    registros = []
    for path in sorted(archivos):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if "texto" in record and "dominio" in record:
                        registros.append({
                            "texto": record["texto"],
                            "dominio": record["dominio"],
                            "seed_file": record.get("seed_file", ""),
                        })
                except json.JSONDecodeError:
                    continue

    print(f"Leídos {len(registros)} registros de {len(archivos)} archivo(s) de Estrategia 5 "
          f"({'validados' if ESTRATEGIA_5_VALIDADA else 'CRUDOS, sin validar'}).")
    return registros, archivos


if __name__ == "__main__":
    print("=== Ejecutando Estrategia 3 — SOLO reordenación (a partir de Estrategia 5) ===")

    if not ESTRATEGIA_5_VALIDADA:
        print("⚠️  Usando datos CRUDOS de la Estrategia 5 (todavía sin validar).")
        print("    Tratá este lote como PRUEBA, no como candidato final.\n")

    disponibles = listar_seeds_disponibles()
    if not disponibles:
        raise RuntimeError("No hay archivos pendientes en raw/estrategia5/.")

    seleccionadas = selector_consola(disponibles)

    semillas, archivos = cargar_datos_estrategia_5(seeds=seleccionadas)
    if not semillas:
        raise RuntimeError("No hay registros utilizables de la Estrategia 5.")

    print(f"Semillas disponibles: {len(semillas)}. "
          f"Hasta {MAX_REORDENACIONES} reordenación(es) por semilla.")

    rutas = generar_estrategia_3(semillas, max_reordenaciones=MAX_REORDENACIONES)

    total_lineas = 0
    for ruta in rutas:
        with open(ruta, "r", encoding="utf-8") as f:
            lineas = [ln for ln in f if ln.strip()]
        total_lineas += len(lineas)
        seed_tag = os.path.basename(os.path.dirname(ruta))
        print(f"    {ruta}: {len(lineas)} reordenaciones ({seed_tag})")

    # Mover archivos de E5 ya procesados para no re-leerlos
    if rutas and archivos:
        for path in archivos:
            seed_dir = os.path.basename(os.path.dirname(path))
            destino_dir = os.path.join(PROCESADOS_E3_DIR, seed_dir)
            os.makedirs(destino_dir, exist_ok=True)
            destino = os.path.join(destino_dir, os.path.basename(path))
            os.rename(path, destino)
        print(f"\nMovidos {len(archivos)} archivo(s) a {PROCESADOS_E3_DIR}")

    print(f"\n=== Completado ===")
    print(f"    Semillas: {len(semillas)} | Máximo posible: {len(semillas) * MAX_REORDENACIONES}")
    print(f"    Reordenaciones reales logradas: {total_lineas}")
