"""
CICLO DATA WRANGLER <-> GOOGLE SHEETS
======================================
Flujo: Lead Dev genera -> vos limpiás -> subís a Sheets ->
       Linguist Hero corrige en Sheets -> releés -> limpiás de nuevo.

Requisitos: pip install gspread google-auth pandas --break-system-packages
Necesitás: credenciales.json (cuenta de servicio) + la hoja compartida con
           el email de esa cuenta de servicio.
"""

import gspread
import pandas as pd
import os
from datetime import datetime
from google.oauth2.service_account import Credentials


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

CARPETA_BACKUP = "backups"


def hacer_backup(df: pd.DataFrame, etiqueta: str):
    """
    Guarda una copia local con timestamp antes de cualquier operación
    riesgosa (limpieza, clear() de Sheets, etc.). No borra backups viejos.
    """
    os.makedirs(CARPETA_BACKUP, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta = os.path.join(CARPETA_BACKUP, f"{timestamp}_{etiqueta}.jsonl")
    df.to_json(ruta, orient="records", lines=True, force_ascii=False)
    print(f"Backup guardado: {ruta}")
    return ruta


def conectar_hoja(nombre_hoja: str, nombre_pestana: str):
    """Conecta con una pestaña específica de tu Google Sheet."""
    creds = Credentials.from_service_account_file("credenciales.json", scopes=SCOPES)
    cliente = gspread.authorize(creds)
    hoja = cliente.open(nombre_hoja)
    return hoja.worksheet(nombre_pestana)


# ─────────────────────────────────────────────────────────────
# PASO 1 — Limpiar lo que trae el Lead Dev (ya sabés hacer esto)
# ─────────────────────────────────────────────────────────────
def limpiar(df: pd.DataFrame) -> pd.DataFrame:
    hacer_backup(df, "antes_de_limpiar")
    df = df.drop_duplicates(subset="texto")
    df = df.dropna(subset=["texto"])
    df["texto"] = df["texto"].str.strip()
    df = df[df["texto"] != ""]
    return df


# ─────────────────────────────────────────────────────────────
# PASO 1.5 — Revisar el borrador ANTES de subir (manual, no automático)
# ─────────────────────────────────────────────────────────────
def revisar_borrador(df: pd.DataFrame) -> bool:
    """
    Muestra un resumen del DataFrame limpio y pide confirmación
    explícita antes de subirlo. Devuelve True solo si vos decís que sí.
    """
    print("=" * 50)
    print(f"BORRADOR — {len(df)} filas listas para subir")
    print("=" * 50)

    # Chequeos básicos que detectan si algo falló en el camino
    vacios = df["texto"].isna().sum() + (df["texto"] == "").sum()
    duplicados = df.duplicated(subset="texto").sum()
    muy_cortos = (df["texto"].str.len() < 3).sum()

    print(f"Textos vacíos:        {vacios}")
    print(f"Duplicados restantes: {duplicados}")
    print(f"Textos sospechosamente cortos (<3 caracteres): {muy_cortos}")
    print("-" * 50)

    # Muestra real del contenido, no solo números
    print("Primeras 10 filas:")
    print(df.head(10).to_string())
    print("-" * 50)
    print("Últimas 5 filas:")
    print(df.tail(5).to_string())
    print("=" * 50)

    if vacios > 0 or muy_cortos > 0:
        print("⚠️  Hay filas sospechosas — revisá antes de confirmar.")

    respuesta = input("\n¿Subir este borrador a Sheets? (s/n): ").strip().lower()
    return respuesta == "s"


# ─────────────────────────────────────────────────────────────
# PASO 1.5 — Control previo: detectar si algo salió mal SIN
#            revisar fila por fila. Esto es lo que evita mandar
#            basura al Linguist Hero por una función que falló
#            en silencio.
# ─────────────────────────────────────────────────────────────
def revisar_antes_de_subir(df_antes: pd.DataFrame, df_despues: pd.DataFrame) -> bool:
    """
    Devuelve True si el DataFrame parece razonable para subir.
    Todas las verificaciones son vectorizadas (O(n), sin loops fila
    por fila) para que no importe si son 50 o 5000 registros.
    """
    print("=" * 50)
    print("REPORTE DE CONTROL — antes de subir a Sheets")
    print("=" * 50)

    # 1. ¿La limpieza se comió TODO? (síntoma clásico de función rota)
    print(f"Filas antes de limpiar:  {len(df_antes)}")
    print(f"Filas después de limpiar: {len(df_despues)}")
    if len(df_despues) == 0:
        print("🚨 ALERTA: quedaron 0 filas. Algo rompió el filtro entero.")
        return False

    perdidas_pct = (1 - len(df_despues) / len(df_antes)) * 100 if len(df_antes) else 0
    if perdidas_pct > 50:
        print(f"⚠️  Se perdió el {perdidas_pct:.1f}% de las filas — revisá si es esperable.")

    # 2. ¿Hay nulos que se colaron?
    nulos = df_despues["texto"].isna().sum()
    if nulos > 0:
        print(f"🚨 ALERTA: {nulos} filas con texto nulo pasaron el filtro.")
        return False

    # 3. Longitudes raras (textos vacíos disfrazados de espacio, o
    #    generaciones gigantes que probablemente sean basura del LLM)
    largos = df_despues["texto"].str.len()
    print(f"Longitud de texto — min: {largos.min()}, media: {largos.mean():.1f}, max: {largos.max()}")
    sospechosos = df_despues[(largos < 2) | (largos > 300)]
    if len(sospechosos) > 0:
        print(f"⚠️  {len(sospechosos)} filas con longitud sospechosa (muy corta o muy larga).")

    # 4. Duplicados que sobrevivieron (dedup no funcionó del todo)
    dup_restantes = df_despues["texto"].duplicated().sum()
    if dup_restantes > 0:
        print(f"🚨 ALERTA: {dup_restantes} duplicados todavía presentes — revisá drop_duplicates().")
        return False

    # 5. Muestra al azar para un vistazo humano rápido (no todo el dataset)
    n_muestra = min(5, len(df_despues))
    print(f"\nMuestra al azar de {n_muestra} filas para revisar a ojo:")
    print(df_despues.sample(n_muestra)[["texto", "dominio"]].to_string(index=False))

    print("=" * 50)
    return True


# ─────────────────────────────────────────────────────────────
# PASO 2 — Subir el DataFrame limpio a Sheets, para que el
#          Linguist Hero lo vea y corrija ahí
# ─────────────────────────────────────────────────────────────
def subir_a_sheets(df: pd.DataFrame, nombre_hoja: str, nombre_pestana: str):
    pestana = conectar_hoja(nombre_hoja, nombre_pestana)

    # Backup de lo que YA está en Sheets, antes de borrarlo con clear()
    datos_previos = pestana.get_all_records()
    if datos_previos:
        hacer_backup(pd.DataFrame(datos_previos), f"sheets_antes_de_clear_{nombre_pestana}")

    pestana.clear()  # ahora sí, con respaldo de lo que había

    # Aseguramos las columnas que el Linguist Hero va a completar.
    # texto_corregido: si la oración está mal, el Linguist Hero la
    # reescribe acá en vez de solo calificarla mal y listo.
    for col in ["sintaxis", "semantica", "texto_corregido", "comentario"]:
        if col not in df.columns:
            df[col] = ""

    # gspread necesita listas de listas: encabezados + filas
    valores = [df.columns.tolist()] + df.values.tolist()
    pestana.update(valores)
    print(f"Subidas {len(df)} filas a la pestaña '{nombre_pestana}'.")


# ─────────────────────────────────────────────────────────────
# PASO 3 — Releer la hoja después de que el Linguist Hero
#          corrigió/calificó (sintaxis, semántica, comentario)
# ─────────────────────────────────────────────────────────────
def leer_de_sheets(nombre_hoja: str, nombre_pestana: str) -> pd.DataFrame:
    pestana = conectar_hoja(nombre_hoja, nombre_pestana)
    registros = pestana.get_all_records()  # ya viene como lista de diccionarios
    df = pd.DataFrame(registros)
    print(f"Leídas {len(df)} filas de la pestaña '{nombre_pestana}'.")
    return df


# ─────────────────────────────────────────────────────────────
# PASO 0 — ANTES de subir un lote nuevo: sacar lo que ya fue
#          revisado en un lote anterior, para que el Linguist
#          Hero no pierda tiempo recalificando lo mismo
# ─────────────────────────────────────────────────────────────
def filtrar_ya_revisados(df_nuevo: pd.DataFrame, carpeta_acumulado: str = ".") -> pd.DataFrame:
    """
    Compara contra TODO lo ya acumulado (las dos estrategias juntas,
    aunque se guarden en archivos separados) — un texto repetido no
    debería colarse dos veces, sin importar qué estrategia lo generó.
    """
    import difflib
    import glob

    archivos = glob.glob(os.path.join(carpeta_acumulado, "dataset_acumulado_estrategia*.jsonl"))
    if not archivos:
        return df_nuevo  # todavía no hay nada acumulado, no hay nada que filtrar

    ya_vistos = []
    for archivo in archivos:
        ya_vistos.extend(pd.read_json(archivo, lines=True)["texto"].tolist())

    def es_repetido(texto):
        return any(
            difflib.SequenceMatcher(None, texto, visto).ratio() > 0.9
            for visto in ya_vistos
        )

    antes = len(df_nuevo)
    df_filtrado = df_nuevo[~df_nuevo["texto"].apply(es_repetido)]
    print(f"[filtro contra acumulado] {antes - len(df_filtrado)} filas descartadas "
          f"por ya haber sido revisadas en un lote anterior (cualquier estrategia).")
    return df_filtrado


def mover_a_procesados(ruta_lote_raw: str):
    """Mueve el lote de raw/ a procesados/ una vez que ya lo subiste a Sheets."""
    import shutil
    os.makedirs("procesados", exist_ok=True)
    destino = os.path.join("procesados", os.path.basename(ruta_lote_raw))
    shutil.move(ruta_lote_raw, destino)
    print(f"Movido a procesados/: {destino}")


def separar_rechazados(df_calificado: pd.DataFrame, umbral_minimo: int = 4) -> pd.DataFrame:
    """
    Descarte puro: calificación baja Y sin ningún intento de corrección.
    (Todo lo que SÍ tuvo corrección, apruebe o no, ya lo captura
    separar_para_regenerar() — no se repite acá.)
    """
    df_calificado["sintaxis"] = pd.to_numeric(df_calificado["sintaxis"], errors="coerce")
    df_calificado["semantica"] = pd.to_numeric(df_calificado["semantica"], errors="coerce")
    tiene_correccion = df_calificado["texto_corregido"].str.strip() != ""

    rechazados = df_calificado[
        ((df_calificado["sintaxis"] < umbral_minimo) | (df_calificado["semantica"] < umbral_minimo))
        & (~tiene_correccion)
    ]
    print(f"{len(rechazados)} filas descartadas sin corrección — diagnóstico puro para el rol de generación.")
    return rechazados


# ─────────────────────────────────────────────────────────────
# PASO 4 — Limpiar de nuevo con lo que corrigió el Linguist Hero
#          (ej. sacar lo que calificó bajo, o quedarte solo con
#          lo aprobado)
# ─────────────────────────────────────────────────────────────
def limpiar_post_validacion(df: pd.DataFrame, umbral_minimo: int = 4) -> pd.DataFrame:
    """
    Filtra lo que pasa DIRECTO al dataset final: solo lo aprobado que
    NO tuvo ninguna corrección manual. Todo lo corregido, sin importar
    el puntaje, se maneja aparte con separar_para_regenerar().
    """
    df["sintaxis"] = pd.to_numeric(df["sintaxis"], errors="coerce")
    df["semantica"] = pd.to_numeric(df["semantica"], errors="coerce")
    df["fue_corregido"] = df["texto_corregido"].str.strip() != ""

    aprobados_sin_correccion = df[
        (df["sintaxis"] >= umbral_minimo)
        & (df["semantica"] >= umbral_minimo)
        & (~df["fue_corregido"])
    ].copy()
    aprobados_sin_correccion["texto_final"] = aprobados_sin_correccion["texto"]

    print(f"{len(aprobados_sin_correccion)} de {len(df)} filas aprobadas SIN corrección "
          f"(van directo al dataset).")
    return aprobados_sin_correccion


def separar_para_regenerar(df: pd.DataFrame) -> pd.DataFrame:
    """
    TODA fila que el Linguist Hero corrigió, sin importar el puntaje.
    No entra al dataset tal cual — vuelve al rol de generación como
    insumo para producir una versión nueva, generada por la estrategia
    correspondiente (no escrita a mano).
    """
    df["fue_corregido"] = df["texto_corregido"].str.strip() != ""
    para_regenerar = df[df["fue_corregido"]][
        ["texto", "texto_corregido", "dominio", "estrategia", "comentario"]
    ]
    print(f"{len(para_regenerar)} filas corregidas — vuelven al rol de generación, "
          f"no entran directo al dataset.")
    return para_regenerar


def separar_dorados_para_lead_dev(df_aprobado: pd.DataFrame) -> pd.DataFrame:
    """
    De lo ya aprobado, separa lo calificado 5/5 — esto es lo que le
    devolvés a Alex como nuevos ejemplos few-shot, usando SIEMPRE el
    texto_final (ya con la corrección aplicada si hubo alguna).
    """
    dorados = df_aprobado[
        (df_aprobado["sintaxis"] == 5) & (df_aprobado["semantica"] == 5)
    ]
    print(f"{len(dorados)} filas doradas (5/5) para pasarle a Alex como few-shot.")
    return dorados[["texto_final", "dominio"]].rename(columns={"texto_final": "texto"})


def agregar_a_acumulado(df_aprobado: pd.DataFrame, carpeta_acumulado: str = "."):
    """
    Suma este lote ya aprobado al dataset consolidado — SEPARADO por
    estrategia. Genera dataset_acumulado_estrategia3.jsonl y
    dataset_acumulado_estrategia5.jsonl, nunca mezclados.
    """
    for valor_estrategia, grupo in df_aprobado.groupby("estrategia"):
        nuevo = grupo[["texto_final", "dominio", "estrategia", "sintaxis", "semantica"]].rename(
            columns={"texto_final": "texto"}
        )
        ruta = os.path.join(carpeta_acumulado, f"dataset_acumulado_estrategia{valor_estrategia}.jsonl")
        if os.path.exists(ruta):
            existente = pd.read_json(ruta, lines=True)
            combinado = pd.concat([existente, nuevo], ignore_index=True)
        else:
            combinado = nuevo
        combinado.to_json(ruta, orient="records", lines=True, force_ascii=False)
        print(f"Estrategia {valor_estrategia}: acumulado ahora tiene {len(combinado)} filas ({ruta}).")


# ─────────────────────────────────────────────────────────────
# EJEMPLO DE USO COMPLETO
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    NOMBRE_HOJA = "Dataset Hackathon Guaraní"  # nombre exacto de tu Google Sheet
    PESTANA = "para_validar"

    # 1. Esto viene del Lead Dev (simulado acá)
    generado = pd.DataFrame([
        {"texto": "Jagua ho'úta pira ko'ẽrõ", "dominio": "vida_cotidiana"},
        {"texto": "Jagua ho'úta pira ko'ẽrõ", "dominio": "vida_cotidiana"},  # duplicado
        {"texto": "Ko'ẽrõ oky", "dominio": "clima"},
    ])

    # 2. Vos limpiás PRIMERO (dentro del lote)
    df_limpio = limpiar(generado)

    # 2.1. Después filtrás contra lo YA acumulado (entre lotes)
    CARPETA_ACUMULADO = "."
    df_limpio = filtrar_ya_revisados(df_limpio, CARPETA_ACUMULADO)

    # 2.5. Control automático ANTES de subir — acá está la respuesta
    #      a "quiero ver un borrador antes de mandar, por si algo falló"
    ok = revisar_antes_de_subir(generado, df_limpio)

    if not ok:
        print("\n⛔ El reporte encontró problemas. NO se sube. Revisá la limpieza primero.")
    else:
        respuesta = input("\n¿Todo se ve bien? Confirmá para subir a Sheets (s/n): ")
        if respuesta.lower() == "s":
            subir_a_sheets(df_limpio, NOMBRE_HOJA, PESTANA)
        else:
            print("Cancelado. Ajustá lo que haga falta y volvé a correr.")

    print("\n>>> Ahora el Linguist Hero completa sintaxis/semántica/texto_corregido en Sheets <<<")
    print(">>> Cuando termine, corré la parte de abajo <<<\n")

    CARPETA_ACUMULADO = "."
    RUTA_LOTE_RAW = "raw/lote_001.jsonl"  # ajustar al nombre real del lote

    # Descomentar cuando el Linguist Hero termine de calificar/corregir:
    # df_calificado = leer_de_sheets(NOMBRE_HOJA, PESTANA)
    #
    # # 1. Solo lo aprobado SIN ninguna corrección entra directo al dataset
    # df_aprobado_directo = limpiar_post_validacion(df_calificado, umbral_minimo=4)
    #
    # # 2. Descarte puro: calificación baja Y sin corrección — diagnóstico
    # rechazados = separar_rechazados(df_calificado, umbral_minimo=4)
    #
    # # 3. TODA fila corregida (apruebe o no el puntaje) vuelve al rol de
    # #    generación, no entra directo al dataset tal cual quedó escrita
    # para_regenerar = separar_para_regenerar(df_calificado)
    #
    # # 4. Sumar SOLO lo aprobado sin corrección al dataset final
    # agregar_a_acumulado(df_aprobado_directo, CARPETA_ACUMULADO)
    #
    # # 5. Guardar rechazados puros — diagnóstico para el rol de generación
    # os.makedirs("rechazados", exist_ok=True)
    # rechazados.to_json("rechazados/lote_001_rechazado.jsonl", orient="records", lines=True, force_ascii=False)
    #
    # # 6. Dorados (5/5, sin corrección) — se ACUMULAN en feedback/dorados.jsonl,
    # #    no se pisan lote a lote
    # dorados = separar_dorados_para_lead_dev(df_aprobado_directo)
    # os.makedirs("feedback", exist_ok=True)
    # if os.path.exists("feedback/dorados.jsonl"):
    #     dorados_previos = pd.read_json("feedback/dorados.jsonl", lines=True)
    #     dorados = pd.concat([dorados_previos, dorados], ignore_index=True)
    # dorados.to_json("feedback/dorados.jsonl", orient="records", lines=True, force_ascii=False)
    #
    # # 7. Correcciones — también se ACUMULAN en feedback/para_regenerar.jsonl.
    # #    Una vez que el Lead Dev regenera y esa versión nueva aprueba,
    # #    conviene limpiar este archivo para no regenerar dos veces lo mismo.
    # if os.path.exists("feedback/para_regenerar.jsonl"):
    #     previas = pd.read_json("feedback/para_regenerar.jsonl", lines=True)
    #     para_regenerar = pd.concat([previas, para_regenerar], ignore_index=True)
    # para_regenerar.to_json("feedback/para_regenerar.jsonl", orient="records", lines=True, force_ascii=False)
    #
    # # 8. Mover el lote original de raw/ a procesados/ (ya no se vuelve a tocar)
    # mover_a_procesados(RUTA_LOTE_RAW)