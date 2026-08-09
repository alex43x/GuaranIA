"""
workers.py
==============
Utilidad compartida para paralelizar llamadas a APIs de LLM (Gemini, Azure)
con un pool de threads, en vez de hacerlas una por una. Pensada para reemplazar
loops secuenciales de requests en cualquier script (strategy_pruebas.py,
diccionario_estrategia3.py, etc.) sin repetir la lógica de ThreadPoolExecutor
en cada uno.

Configurable vía MAX_WORKERS en .env (default 5).
"""

import os
import concurrent.futures
from dotenv import load_dotenv

load_dotenv()

MAX_WORKERS = int(os.getenv("MAX_WORKERS", "5"))


def mapear_paralelo(items: list, funcion, max_workers: int | None = None, on_completado=None) -> list:
    """
    Aplica 'funcion' a cada elemento de 'items' usando un pool de threads
    (ideal para I/O de red, como llamadas a Gemini/Azure).

    Devuelve los resultados en el MISMO orden que 'items', aunque la
    ejecución interna sea concurrente. Si 'funcion' lanza una excepción
    para algún item, esa excepción se propaga al llamador (igual que
    pasaría en un loop secuencial normal).

    Si se pasa 'on_completado(indice, item, resultado)', se llama en el
    thread principal apenas termina CADA item (en el orden en que van
    completando, no en el orden original) — sirve para imprimir progreso
    en vivo en vez de quedarse mudo hasta que termine todo el lote.
    """
    max_workers = max_workers or MAX_WORKERS
    if not items:
        return []
    resultados = [None] * len(items)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futuros = {executor.submit(funcion, item): idx for idx, item in enumerate(items)}
        for futuro in concurrent.futures.as_completed(futuros):
            idx = futuros[futuro]
            resultado = futuro.result()
            resultados[idx] = resultado
            if on_completado is not None:
                on_completado(idx, items[idx], resultado)
    return resultados
