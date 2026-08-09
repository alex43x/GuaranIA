"""
VALIDAR RAWS — Detección global de textos duplicados + comparación contra corpus
================================================================================
Lee recursivamente todos los .jsonl de raw/estrategia3/, raw/estrategia5/ y
seeds/corpus/corpus-main/data/raw/, normaliza los textos y detecta:
  1. Duplicados internos entre raws (estrategia3 ↔ estrategia5)
  2. Coincidencias de raws contra el corpus externo

Permite eliminar los duplicados de los archivos raw previa confirmación.
Guarda el reporte completo en reporte_duplicados.txt.

No llama a ningún LLM ni API externa.

Uso:
    python validar_raws.py
"""

import os
import re
import json
import glob
import shutil
import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed


RAW_CARPETAS = ["raw/estrategia3", "raw/estrategia5"]
CORPUS_CARPETA = "seeds/corpus/corpus-main/data/raw"
REPORTE_TXT = "reporte_duplicados.txt"

_RE_NORMALIZAR = re.compile(r'[!?¡¿,.;:…]')
_RE_REPETIDOS = re.compile(r'([!?¡¿,.;:…])\1+')


def normalizar_texto(texto: str) -> str:
    t = texto.lower().strip()
    t = _RE_REPETIDOS.sub(r'\1', t)
    t = _RE_NORMALIZAR.sub(' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def extraer_texto_corpus(reg: dict) -> str:
    for key in ("text", "sentence", "content"):
        val = reg.get(key, "")
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _contar_y_leer(ruta: str) -> list[str]:
    """Lee un .jsonl y devuelve lista de textos normalizados + clave original."""
    textos: list[str] = []
    with open(ruta, "r", encoding="utf-8", errors="replace") as f:
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
            textos.append(texto)
    return textos


def _contar_y_leer_corpus(ruta: str) -> list[tuple[str, str]]:
    """Lee un .jsonl del corpus, devuelve (clave_normalizada, texto_original)."""
    resultados: list[tuple[str, str]] = []
    with open(ruta, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                reg = json.loads(line.strip())
            except json.JSONDecodeError:
                continue
            texto = extraer_texto_corpus(reg)
            if not texto:
                continue
            clave = normalizar_texto(texto)
            if clave:
                resultados.append((clave, texto))
    return resultados


def cargar_corpus() -> set[str] | None:
    """Carga todos los textos del corpus en un set normalizado. Retorna None si no hay corpus."""
    if not os.path.isdir(CORPUS_CARPETA):
        print(f"[CORPUS] No se encontró '{CORPUS_CARPETA}'. Se omite comparación con corpus.")
        return None

    archivos = sorted(glob.glob(os.path.join(CORPUS_CARPETA, "*.jsonl")))
    archivos_validos = []
    for ruta in archivos:
        size = os.path.getsize(ruta)
        if size < 500:
            continue
        with open(ruta, "r", encoding="utf-8", errors="replace") as f:
            first = f.readline()
            if first.startswith("version https://git-lfs"):
                continue
        archivos_validos.append(ruta)

    if not archivos_validos:
        print(f"[CORPUS] Todos los archivos son punteros LFS vacíos. Ejecutá 'git lfs pull' en seeds/corpus/corpus-main/.")
        print(f"[CORPUS] Se omite comparación con corpus.")
        return None

    print(f"[CORPUS] Cargando {len(archivos_validos)} archivos...")

    corpus_set: set[str] = set()

    with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 4)) as ex:
        futuros = {ex.submit(_contar_y_leer_corpus, r): r for r in archivos_validos}
        completados = 0
        for f in as_completed(futuros):
            completados += 1
            resultados = f.result()
            for clave, _texto in resultados:
                corpus_set.add(clave)
            print(f"   [{completados}/{len(archivos_validos)}] {os.path.basename(futuros[f])}  "
                  f"→ {len(resultados)} textos  (set acumulado: {len(corpus_set)})", flush=True)

    print(f"\n[CORPUS] Total de textos únicos normalizados en corpus: {len(corpus_set):,}")
    return corpus_set


def cargar_raws_paralelo(corpus_set: set[str] | None):
    print("\n[RAWS] Escaneando archivos...")

    todos_los_archivos: list[tuple[str, str]] = []
    for carpeta in sorted(RAW_CARPETAS):
        estrategia = "estrategia3" if "estrategia3" in carpeta else "estrategia5"
        nombre_carpeta = carpeta.replace("raw/", "")
        archivos = sorted(glob.glob(os.path.join(carpeta, "**", "*.jsonl"), recursive=True))
        for ruta in archivos:
            todos_los_archivos.append((ruta, estrategia))
    print(f"   {len(todos_los_archivos)} archivos encontrados.")

    vistos_raws: dict[str, str] = {}
    corpus_dups: dict[str, list[tuple[str, str, str, str, str]]] = defaultdict(list)

    stats_por_archivo: list[dict] = []
    por_estrategia: dict[str, dict[str, int]] = {
        "estrategia3": {"total": 0, "dup_internos": 0, "dup_corpus": 0, "unicos": 0},
        "estrategia5": {"total": 0, "dup_internos": 0, "dup_corpus": 0, "unicos": 0},
    }
    dup_cruzados: dict[str, set[str]] = {"e3": set(), "e5": set()}

    contador = [0]

    with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 4)) as ex:
        futuros = {ex.submit(_contar_y_leer, ruta): (ruta, estrategia) for ruta, estrategia in todos_los_archivos}
        for f in as_completed(futuros):
            ruta, estrategia = futuros[f]
            rel = os.path.relpath(ruta)
            textos = f.result()
            contador[0] += 1

            total_archivo = len(textos)
            dup_internos = 0
            dup_corpus = 0
            unicos = 0
            dups_detalle: list[tuple[str, str, str]] = []

            for texto in textos:
                clave = normalizar_texto(texto)

                es_corpus_dup = False
                if corpus_set is not None and clave in corpus_set:
                    dup_corpus += 1
                    es_corpus_dup = True

                if clave in vistos_raws:
                    dup_internos += 1
                    origen = vistos_raws[clave]
                    dups_detalle.append((clave, texto[:80], origen))
                    if estrategia == "estrategia3":
                        dup_cruzados["e3"].add(clave)
                    else:
                        dup_cruzados["e5"].add(clave)
                else:
                    if not es_corpus_dup:
                        vistos_raws[clave] = rel
                    unicos += 1

                if es_corpus_dup and clave not in vistos_raws:
                    vistos_raws[clave] = f"CORPUS (visto antes en corpus externo)"

            por_estrategia[estrategia]["total"] += total_archivo
            por_estrategia[estrategia]["dup_internos"] += dup_internos
            por_estrategia[estrategia]["dup_corpus"] += dup_corpus
            por_estrategia[estrategia]["unicos"] += unicos - dup_corpus if unicos >= dup_corpus else 0

            stats_por_archivo.append({
                "archivo": rel,
                "estrategia": estrategia,
                "total": total_archivo,
                "dup_internos": dup_internos,
                "dup_corpus": dup_corpus,
                "unicos": max(0, unicos - dup_corpus),
            })

            if dups_detalle:
                corpus_dups[estrategia].extend(
                    (estrategia, rel, clave, texto_orig, origen)
                    for clave, texto_orig, origen in dups_detalle
                )

            status = ""
            if total_archivo > 0:
                parts = []
                if dup_internos:
                    parts.append(f"internos={dup_internos}")
                if dup_corpus:
                    parts.append(f"corpus={dup_corpus}")
                if parts:
                    status = f"  [!] {', '.join(parts)}"
                print(f"  [{contador[0]:>4d}/{len(todos_los_archivos)}] [{estrategia}] {rel}  "
                      f"total={total_archivo}{status}", flush=True)

    return stats_por_archivo, por_estrategia, dup_cruzados, corpus_dups, vistos_raws


def guardar_reporte(stats_por_archivo, por_estrategia, dup_cruzados, corpus_dups, corpus_set):
    print(f"\n[REPORTE] Guardando en {REPORTE_TXT}...")

    total_general = sum(e["total"] for e in por_estrategia.values())
    total_dup_int = sum(e["dup_internos"] for e in por_estrategia.values())
    total_dup_corpus = sum(e["dup_corpus"] for e in por_estrategia.values())

    with open(REPORTE_TXT, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("REPORTE DE DUPLICADOS — VALIDACIÓN DE RAWS\n")
        f.write(f"Generado: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 70 + "\n\n")

        if corpus_set is not None:
            f.write(f"Corpus cargado: {len(corpus_set):,} textos únicos normalizados\n\n")

        f.write("SECCIÓN 1 — DETALLE POR ARCHIVO\n")
        f.write("=" * 70 + "\n\n")
        for s in stats_por_archivo:
            if s["total"] == 0:
                continue
            f.write(f"  [{s['estrategia']}] {s['archivo']}\n")
            f.write(f"    Total: {s['total']:>5d}  "
                    f"Dup. internos: {s['dup_internos']:>4d}  "
                    f"Dup. corpus: {s['dup_corpus']:>4d}  "
                    f"Únicos: {s['unicos']:>5d}\n")

        f.write("\nSECCIÓN 2 — RESUMEN POR ESTRATEGIA\n")
        f.write("=" * 70 + "\n\n")
        for est in ["estrategia3", "estrategia5"]:
            s = por_estrategia[est]
            if s["total"] == 0:
                continue
            tasa_int = (s["dup_internos"] / s["total"] * 100) if s["total"] > 0 else 0
            tasa_corpus = (s["dup_corpus"] / s["total"] * 100) if s["total"] > 0 else 0
            f.write(f"  {est}:\n")
            f.write(f"    Total:              {s['total']:>6d}\n")
            f.write(f"    Dup. internos:      {s['dup_internos']:>6d}  ({tasa_int:.1f}%)\n")
            f.write(f"    Dup. vs corpus:     {s['dup_corpus']:>6d}  ({tasa_corpus:.1f}%)\n")
            f.write(f"    Únicos netos:       {s['unicos']:>6d}\n\n")

        e3_set = dup_cruzados.get("e3", set())
        e5_set = dup_cruzados.get("e5", set())
        ambos = e3_set & e5_set

        f.write("SECCIÓN 3 — DUPLICADOS CRUZADOS ENTRE ESTRATEGIAS\n")
        f.write("=" * 70 + "\n\n")
        f.write(f"  Solo en estrategia3:  {len(e3_set - e5_set):>6d}\n")
        f.write(f"  Solo en estrategia5:  {len(e5_set - e3_set):>6d}\n")
        f.write(f"  En ambas estrategias: {len(ambos):>6d}\n\n")

        if corpus_dups:
            f.write("SECCIÓN 4 — MUESTRA DE DUPLICADOS INTERNOS (primeros 100)\n")
            f.write("=" * 70 + "\n\n")
            count = 0
            for est in ["estrategia3", "estrategia5"]:
                if est not in corpus_dups:
                    continue
                for estrategia, archivo, clave, texto_orig, origen in corpus_dups[est]:
                    if count >= 100:
                        break
                    f.write(f"  [{estrategia}] {archivo}\n")
                    f.write(f"    Texto:     {texto_orig}\n")
                    f.write(f"    Ya visto en: {origen}\n\n")
                    count += 1
                if count >= 100:
                    break

        f.write("SECCIÓN 5 — TOTAL GENERAL\n")
        f.write("=" * 70 + "\n\n")
        tasa_int = (total_dup_int / total_general * 100) if total_general > 0 else 0
        f.write(f"  Total registros:        {total_general:>8d}\n")
        f.write(f"  Duplicados internos:    {total_dup_int:>8d}  ({tasa_int:.1f}%)\n")
        if corpus_set is not None:
            tasa_c = (total_dup_corpus / total_general * 100) if total_general > 0 else 0
            f.write(f"  Coincidencias corpus:   {total_dup_corpus:>8d}  ({tasa_c:.1f}%)\n")
        f.write(f"  Únicos netos:           {total_general - total_dup_int - total_dup_corpus:>8d}\n")

    print(f"[REPORTE] Listo: {REPORTE_TXT}")


def eliminar_duplicados(vistos_raws: dict[str, str], corpus_set: set[str] | None):
    print("\n" + "=" * 70)
    print("ELIMINACIÓN DE DUPLICADOS")
    print("=" * 70)

    archivos_raw = []
    for carpeta in sorted(RAW_CARPETAS):
        archivos_raw.extend(glob.glob(os.path.join(carpeta, "**", "*.jsonl"), recursive=True))

    if not archivos_raw:
        print("No hay archivos raw para procesar.")
        return

    backup_dir = f"backups/raw_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(backup_dir, exist_ok=True)

    total_eliminadas = 0
    total_lineas = 0

    for ruta in archivos_raw:
        rel = os.path.relpath(ruta)
        lineas_ok: list[str] = []
        eliminadas_archivo = 0

        with open(ruta, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.strip():
                    lineas_ok.append(line)
                    continue
                try:
                    reg = json.loads(line.strip())
                except json.JSONDecodeError:
                    lineas_ok.append(line)
                    continue

                texto = reg.get("texto", "").strip()
                if not texto:
                    lineas_ok.append(line)
                    total_lineas += 1
                    continue

                clave = normalizar_texto(texto)
                total_lineas += 1

                debe_eliminar = False
                if corpus_set is not None and clave in corpus_set:
                    debe_eliminar = True
                if clave in vistos_raws and vistos_raws[clave] != rel:
                    debe_eliminar = True

                if debe_eliminar:
                    eliminadas_archivo += 1
                else:
                    lineas_ok.append(line)

        if eliminadas_archivo > 0:
            shutil.copy2(ruta, os.path.join(backup_dir, os.path.basename(ruta)))
            tmp = ruta + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.writelines(lineas_ok)
            os.replace(tmp, ruta)
            total_eliminadas += eliminadas_archivo
            print(f"  {rel}: {eliminadas_archivo} líneas eliminadas")

    print(f"\n  Backup: {backup_dir}")
    print(f"  Total líneas eliminadas: {total_eliminadas} de {total_lineas}")
    print("=" * 70)


def main():
    print("=" * 70)
    print("VALIDACIÓN DE RAWS — DETECCIÓN GLOBAL DE TEXTOS DUPLICADOS")
    print("=" * 70)

    corpus_set = cargar_corpus()

    stats, por_est, dup_cruz, corpus_dups, vistos_raws = cargar_raws_paralelo(corpus_set)

    guardar_reporte(stats, por_est, dup_cruz, corpus_dups, corpus_set)

    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    for est in ["estrategia3", "estrategia5"]:
        s = por_est[est]
        if s["total"] == 0:
            continue
        print(f"\n  {est}:")
        print(f"    Total registros:    {s['total']:>6d}")
        print(f"    Dup. internos:      {s['dup_internos']:>6d}")
        if corpus_set is not None:
            print(f"    Dup. vs corpus:     {s['dup_corpus']:>6d}")
        print(f"    Únicos netos:       {s['unicos']:>6d}")

    total = sum(e["total"] for e in por_est.values())
    total_dup = sum(e["dup_internos"] for e in por_est.values())
    total_corpus = sum(e["dup_corpus"] for e in por_est.values())
    print(f"\n  TOTAL GENERAL: {total} | Dup. internos: {total_dup} | "
          f"Dup. vs corpus: {total_corpus} | Únicos: {total - total_dup - total_corpus}")

    print("\n" + "=" * 70)
    print(f"Reporte completo guardado en: {REPORTE_TXT}")
    print("=" * 70)

    if total_dup + total_corpus == 0:
        print("\nNo se encontraron duplicados. Nada que eliminar.")
        return

    print(f"\nSe encontraron {total_dup} duplicados internos", end="")
    if corpus_set is not None:
        print(f" y {total_corpus} coincidencias con el corpus", end="")
    print(".\n")

    resp = input("¿Eliminar todos los duplicados de los archivos raw? (s/n): ").strip().lower()
    if resp == "s":
        eliminar_duplicados(vistos_raws, corpus_set)
        print("\nDuplicados eliminados. Volvé a correr el script para verificar.")
    else:
        print("\nNo se eliminó nada.")


if __name__ == "__main__":
    main()
