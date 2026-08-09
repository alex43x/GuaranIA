"""
GENERAR ENTREGABLE — Extrae textos de raw/
============================================
Lee todos los .jsonl en raw/estrategia{N}/, extrae el campo "texto",
deduplica y escribe entregable_estrategia{N}.txt con una oración por línea.

Genera dos archivos: uno para Estrategia 3 y otro para Estrategia 5.

Uso:
    python generar_entregable.py
"""

import os
import json
import glob
import re


def normalizar(texto: str) -> str:
    t = texto.lower().strip()
    t = re.sub(r'[!?¡¿,.;:…"\'""]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def generar_entregable(carpeta: str, archivo_salida: str):
    textos_unicos = []
    vistos = set()
    total = 0

    archivos = sorted(glob.glob(os.path.join(carpeta, "**", "*.jsonl"), recursive=True))
    for ruta in archivos:
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
                total += 1
                clave = normalizar(texto)
                if clave not in vistos:
                    vistos.add(clave)
                    textos_unicos.append(texto)

    with open(archivo_salida, "w", encoding="utf-8") as f:
        for texto in textos_unicos:
            f.write(texto + "\n")

    print(f"  [{os.path.basename(archivo_salida)}] Total registros leídos: {total}")
    print(f"  [{os.path.basename(archivo_salida)}] Textos únicos:         {len(textos_unicos)}")
    print(f"  [{os.path.basename(archivo_salida)}] Duplicados omitidos:   {total - len(textos_unicos)}")
    print(f"  [{os.path.basename(archivo_salida)}] Guardado en: {archivo_salida}\n")


if __name__ == "__main__":
    print("=== Generando entregables ===\n")

    generar_entregable("raw/estrategia3", "estrategia3.txt")
    generar_entregable("raw/estrategia5", "estrategia5.txt")

    print("=== Listo ===")
