"""Test de funciones puras de data_wrangler (sin conexión a Sheets ni API)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data_wrangler import (
    normalizar_texto, deduplicar_por_texto, clasificar_por_estrategia,
    _parsear_puntaje, formatear_filas_e3, formatear_filas_e5,
    COLUMNAS_E3, COLUMNAS_E5,
    filtrar_ya_revisados, VALIDACION_MORFOLOGICA
)
import json

print("=== normalizar_texto ===")
assert normalizar_texto("Hola!!") == "hola", f"Fallo: {normalizar_texto('Hola!!')}"
assert normalizar_texto("Sali, corri") == "sali corri"
assert normalizar_texto("¡Mba'eichapa!!!") == "mba'eichapa"
print("  OK")

print("=== deduplicar_por_texto ===")
regs = [
    {"texto": "Hola!!"},
    {"texto": "Hola!!!!"},
    {"texto": "Sali, corri"},
    {"texto": "Sali y corri"},
]
result = deduplicar_por_texto(regs)
assert len(result) == 3, f"Esperaba 3, obtuve {len(result)}"
print("  OK")

print("=== clasificar_por_estrategia ===")
regs = [
    {"texto": "a", "estrategia": "3"},
    {"texto": "b", "estrategia": "5"},
    {"texto": "c", "estrategia": "3"},
    {"texto": "d", "estrategia": "5"},
    {"texto": "e", "estrategia": "3"},
]
e3, e5 = clasificar_por_estrategia(regs)
assert len(e3) == 3 and len(e5) == 2
print("  OK")

print("=== _parsear_puntaje ===")
assert _parsear_puntaje("5") == 5
assert _parsear_puntaje(3) == 3
assert _parsear_puntaje(None) is None
assert _parsear_puntaje("") is None
print("  OK")

print("=== formatear_filas_e3 ===")
regs = [
    {"texto": "Che aguata", "texto_base": "aguata", "tipo_transformacion": "reordenar", "dominio": "vida_cotidiana", "estrategia": "3"},
]
filas = formatear_filas_e3(regs)
assert len(filas) == 1
assert filas[0] == ["Che aguata", "aguata", "reordenar", "vida_cotidiana", "3", "", "", ""]
assert len(filas[0]) == 8
print("  OK")

print("=== formatear_filas_e5 ===")
regs = [
    {"texto": "Ha upei", "dominio": "conectores", "estrategia": "5", "prompt": "Genera una oracion..."},
]
filas = formatear_filas_e5(regs)
assert len(filas) == 1
assert filas[0] == ["Ha upei", "conectores", "5", "Genera una oracion...", "", "", ""]
assert len(filas[0]) == 7
print("  OK")

print("=== COLUMNAS_E3 ===")
assert COLUMNAS_E3 == ["texto", "texto_base", "tipo_transformacion", "dominio", "estrategia",
                        "puntaje_sintaxis", "puntaje_semantica", "correccion"]
print("  OK")

print("=== COLUMNAS_E5 ===")
assert COLUMNAS_E5 == ["texto", "dominio", "estrategia", "prompt",
                        "puntaje_sintaxis", "puntaje_semantica", "correccion"]
print("  OK")

print("\n=== filtrar_ya_revisados (sin archivo) ===")
regs = [{"texto": "a"}, {"texto": "b"}]
assert len(filtrar_ya_revisados(regs)) == 2
print("  OK")

print("=== VALIDACION_MORFOLOGICA ===")
assert VALIDACION_MORFOLOGICA == False
print(f"  OK (valor: {VALIDACION_MORFOLOGICA})")

print("\nTodas las pruebas pasaron.")
