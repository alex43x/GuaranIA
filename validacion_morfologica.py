"""
Validador morfológico para guaraní usando eiru-labs/segmentador-guarani.
Requiere: pip install gradio_client

Uso:
    from validacion_morfologica import validar_morfologia
    ok, motivo = validar_morfologia("Che aguatatahína ko'ẽrõ")
"""

import re

_cliente_morfo = None


def validar_morfologia(texto: str):
    """
    Llama a /segmentar_oracion y clasifica el resultado.
    Retorna (True, "") si aprueba, o (False, motivo) si falla.
    Motivos posibles: sin_candidatos, fallo_morfologico, api_error.
    """
    global _cliente_morfo
    try:
        if _cliente_morfo is None:
            from gradio_client import Client
            _cliente_morfo = Client("eiru-labs/segmentador-guarani")
    except ImportError:
        return False, "api_error: gradio_client no instalado"
    except Exception as e:
        return False, f"api_error: {e}"

    try:
        resultado = _cliente_morfo.predict(
            oracion=texto,
            top_k=1,
            mostrar_alternativas=False,
            api_name="/segmentar_oracion"
        )
    except Exception as e:
        return False, f"api_error: {e}"

    if not resultado or not isinstance(resultado, str):
        return False, "api_error: respuesta vacía o inesperada"

    bloques = re.findall(r'== (.+?) ==\s*\n(.*?)(?=\n== |\Z)', resultado, re.DOTALL)
    if not bloques:
        return False, "sin_candidatos: no se pudo segmentar ninguna palabra"

    palabras_fallo = []
    for palabra, contenido in bloques:
        palabra = palabra.strip()
        candidatos = re.findall(r'(\d+)\.\s+(.+?)\s+\(score:\s*([\d.]+)\)', contenido)
        if not candidatos:
            palabras_fallo.append(palabra)
            continue

        mejor_score = float(candidatos[0][2])
        tiene_raiz = any('[RAIZ]' in c[1] for c in candidatos)

        if mejor_score <= 0:
            palabras_fallo.append(f"{palabra}(score:{mejor_score})")
        elif not tiene_raiz:
            palabras_fallo.append(f"{palabra}(sin_raiz)")

    if palabras_fallo:
        return False, f"fallo_morfologico: {', '.join(palabras_fallo)}"

    return True, ""
