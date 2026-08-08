"""
config_por_fuente.py
========================
ÚNICA RESPONSABILIDAD: la configuración de qué estrategias aplican a
cada archivo semilla (seed_file), decidida por el Linguist Hero según
el registro/dominio de cada corpus. La usan run_strategy_3.py
(reordenamiento) y diccionario_estrategia3.py (sinónimos) — un solo
lugar, para que no se desincronicen dos copias del mismo criterio.
"""

CONFIG_POR_FUENTE = {
    "jojajovai.jsonl": {
        "reordenamiento_habilitado": True,
        "sinonimos_habilitado": True,
        "pos_permitidos": {"sustantivo", "adjetivo"},  # sin verbo: registro periodístico
    },
    "tatoeba.jsonl": {
        "reordenamiento_habilitado": True,   # ← revisar con el Linguist Hero
        "sinonimos_habilitado": True,
        "pos_permitidos": {"sustantivo"},           # ← completar
    },
    "belele.jsonl": {
        "reordenamiento_habilitado": True,   # ← revisar con el Linguist Hero
        "sinonimos_habilitado": True,
        "pos_permitidos": {"verbo"},           # ← completar
    },
    "americasnli.jsonl": {
        "reordenamiento_habilitado": True,   # ← revisar con el Linguist Hero
        "sinonimos_habilitado": True,
        "pos_permitidos": {"sustantivo", "adjetivo", "verbo"},           # ← completar
    },
    "flores-200.jsonl": {
        "reordenamiento_habilitado": True,   # ← revisar con el Linguist Hero
        "sinonimos_habilitado": True,
        "pos_permitidos": {"verbo", "sustantivo"},           # ← completar
    },
}

CONFIG_DEFAULT = {
    "reordenamiento_habilitado": True,
    "sinonimos_habilitado": True,
    "pos_permitidos": {"sustantivo", "verbo", "adjetivo"},
}

def config_para_fuente(seed_file: str) -> dict:
    return CONFIG_POR_FUENTE.get(seed_file, CONFIG_DEFAULT)