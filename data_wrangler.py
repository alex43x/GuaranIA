"""
DATA WRANGLER — Pipeline completo de filtrado, validación y carga a Google Sheets
==================================================================================
FASE 1: raw/ -> validación morfológica -> Sheets (pestañas estrategia_3 / estrategia_5)
FASE 3: Sheets -> clasificación -> dataset_acumulado.jsonl / feedback / rechazados

Requisitos: pip install gspread google-auth gradio_client
Necesita: credenciales.json (Cuenta de Servicio de Google Cloud)
"""

import os
import re
import json
import glob
import shutil
import datetime
import gspread
from google.oauth2.service_account import Credentials

# ─── CONFIGURACIÓN ───
NOMBRE_HOJA = "hackathon-test"
TAB_E3 = "estrategia_3"
TAB_E5 = "estrategia_5"
CARPETA_RAW = "raw"
CARPETA_PROCESADOS = "procesados"
CARPETA_RECHAZADOS = "rechazados"
CARPETA_FEEDBACK = "feedback"
CARPETA_BACKUPS = "backups"
ARCHIVO_DATASET = "dataset_acumulado.jsonl"
ARCHIVO_DORADOS = "feedback/dorados.jsonl"
ARCHIVO_PARA_REGENERAR = "feedback/para_regenerar.jsonl"

CAMPOS_REQUERIDOS = ["texto", "texto_base", "tipo_transformacion", "dominio", "estrategia"]
COLUMNAS_E3 = ["texto", "texto_base", "tipo_transformacion", "dominio", "estrategia",
               "puntaje_sintaxis", "puntaje_semantica", "correccion"]
COLUMNAS_E5 = ["texto", "dominio", "estrategia", "prompt",
               "puntaje_sintaxis", "puntaje_semantica", "correccion"]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

VALIDACION_MORFOLOGICA = False  # Cambiar a cuando se quiera aplicar API externa para correciones con morfologia

# ─── HELPERS ───

def asegurar_carpetas():
    for carpeta in [CARPETA_RAW, CARPETA_PROCESADOS, CARPETA_RECHAZADOS,
                    CARPETA_FEEDBACK, CARPETA_BACKUPS]:
        os.makedirs(carpeta, exist_ok=True)


def backup_raw():
    archivos = glob.glob(os.path.join(CARPETA_RAW, "*.jsonl"))
    if not archivos:
        return
    for anterior in glob.glob(os.path.join(CARPETA_BACKUPS, "raw_*")):
        shutil.rmtree(anterior)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    carpeta_bkp = os.path.join(CARPETA_BACKUPS, f"raw_{ts}")
    os.makedirs(carpeta_bkp, exist_ok=True)
    for archivo in archivos:
        shutil.copy2(archivo, carpeta_bkp)
    print(f"[Wrangler] Backup creado en {carpeta_bkp}")


def normalizar_texto(texto: str) -> str:
    t = texto.lower().strip()
    t = re.sub(r'([!?¡¿,.;:…])\1+', r'\1', t)
    t = re.sub(r'[!?¡¿,.;:…]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

# ─── CONEXIÓN A SHEETS ───

_cliente_sheets = None


def _get_cliente():
    global _cliente_sheets
    if _cliente_sheets is None:
        ruta_creds = "./credenciales.json"
        if not os.path.exists(ruta_creds):
            raise FileNotFoundError("No se encuentra 'credenciales.json' en la raíz del proyecto.")
        creds = Credentials.from_service_account_file(ruta_creds, scopes=SCOPES)
        _cliente_sheets = gspread.authorize(creds)
    return _cliente_sheets


def conectar_a_pestana(nombre_pestana: str, columnas: list[str], crear_si_no_existe: bool = True):
    cliente = _get_cliente()
    hoja = cliente.open(NOMBRE_HOJA)
    try:
        pestana = hoja.worksheet(nombre_pestana)
        primera_fila = pestana.row_values(1)
        if not primera_fila:
            pestana.append_row(columnas)
            print(f"   Pestaña '{nombre_pestana}' existía vacía, cabeceras escritas.")
        return pestana
    except gspread.exceptions.WorksheetNotFound:
        if crear_si_no_existe:
            pestana = hoja.add_worksheet(title=nombre_pestana, rows="1000", cols="10")
            pestana.append_row(columnas)
            print(f"   Pestaña '{nombre_pestana}' creada con cabeceras.")
            return pestana
        raise

# ─── DEDUPLICACIÓN ───

def deduplicar_por_texto(registros: list[dict]) -> list[dict]:
    vistos = set()
    unicos = []
    for reg in registros:
        clave = normalizar_texto(reg.get("texto", ""))
        if clave not in vistos:
            vistos.add(clave)
            unicos.append(reg)
    return unicos

# ─── FILTRADO ───

def filtrar_registros(registros: list[dict]) -> list[dict]:
    registros_aprobados = []
    for reg in registros:
        texto = reg.get("texto", "").strip()

        # --- IMPLEMENTAR FILTROS AQUÍ ---
        es_valido = len(texto) > 0 and texto != reg.get("texto_base", "")
        # --------------------------------

        if es_valido:
            registros_aprobados.append(reg)

    return registros_aprobados

# ─── FILTRADO CONTRA DATASET ACUMULADO ───

def filtrar_ya_revisados(registros: list[dict]) -> list[dict]:
    if not os.path.exists(ARCHIVO_DATASET):
        return registros
    textos_aprobados = set()
    with open(ARCHIVO_DATASET, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    reg = json.loads(line.strip())
                    clave = normalizar_texto(reg.get("texto", ""))
                    if clave:
                        textos_aprobados.add(clave)
                except json.JSONDecodeError:
                    pass
    if not textos_aprobados:
        return registros
    nuevos = []
    for reg in registros:
        if normalizar_texto(reg.get("texto", "")) not in textos_aprobados:
            nuevos.append(reg)
    descartados = len(registros) - len(nuevos)
    if descartados > 0:
        print(f"[Wrangler] Filtrados contra dataset acumulado: {descartados} ya revisados, se saltean.")
    return nuevos

# ─── CLASIFICACIÓN POR ESTRATEGIA ───

def clasificar_por_estrategia(registros: list[dict]) -> tuple[list[dict], list[dict]]:
    e3 = [r for r in registros if str(r.get("estrategia", "")) == "3"]
    e5 = [r for r in registros if str(r.get("estrategia", "")) == "5"]
    return e3, e5

# ─── FORMATEO POR ESTRATEGIA ───

def formatear_filas_e3(registros: list[dict]) -> list[list]:
    filas = []
    for reg in registros:
        fila = [
            reg.get("texto", ""),
            reg.get("texto_base", ""),
            reg.get("tipo_transformacion", ""),
            reg.get("dominio", ""),
            reg.get("estrategia", ""),
            "", "", "",
        ]
        filas.append(fila)
    return filas


def formatear_filas_e5(registros: list[dict]) -> list[list]:
    filas = []
    for reg in registros:
        fila = [
            reg.get("texto", ""),
            reg.get("dominio", ""),
            reg.get("estrategia", ""),
            reg.get("prompt", ""),
            "", "", "",
        ]
        filas.append(fila)
    return filas


def subir_a_pestana(pestana, filas: list[list]):
    if not filas:
        return 0
    pestana.append_rows(filas)
    return len(filas)

# ─── FASE 1: raw -> Sheets ───

def fase1_subir():
    print("=" * 60)
    print("FASE 1: raw -> Sheets")
    print("=" * 60)

    asegurar_carpetas()

    archivos_jsonl = sorted(glob.glob(os.path.join(CARPETA_RAW, "*.jsonl")))
    if not archivos_jsonl:
        print(f"[Wrangler] No se encontraron archivos .jsonl en '{CARPETA_RAW}'.")
        return

    backup_raw()

    print(f"[Wrangler] {len(archivos_jsonl)} archivo(s) en raw/.")
    todos_los_registros = []

    for ruta_archivo in archivos_jsonl:
        nombre = os.path.basename(ruta_archivo)
        print(f"   Leyendo {nombre}...")
        conteo = 0
        with open(ruta_archivo, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    todos_los_registros.append(json.loads(line.strip()))
                    conteo += 1
                except json.JSONDecodeError:
                    print(f"      WARNING: línea {line_num} inválida en {nombre}, se omite.")
        print(f"      {conteo} registros leídos.")

    total = len(todos_los_registros)
    print(f"\n[Wrangler] Registros totales leídos: {total}")

    registros_unicos = deduplicar_por_texto(todos_los_registros)
    dup = total - len(registros_unicos)
    if dup > 0:
        print(f"[Wrangler] Duplicados descartados (por texto normalizado): {dup}")

    registros_sin_revisados = filtrar_ya_revisados(registros_unicos)

    registros_filtrados = filtrar_registros(registros_sin_revisados)
    print(f"[Wrangler] Pasan el filtro: {len(registros_filtrados)}")

    if not registros_filtrados:
        print("[Wrangler] No hay registros para subir.")
        return

    if VALIDACION_MORFOLOGICA:
        from validacion_morfologica import validar_morfologia
        registros_validados = []
        descartes_morfo = []
        print(f"\n[Wrangler] Validando morfología con segmentador-guarani...")
        for i, reg in enumerate(registros_filtrados):
            texto = reg.get("texto", "")
            ok, motivo = validar_morfologia(texto)
            if ok:
                registros_validados.append(reg)
            else:
                descartes_morfo.append((texto, motivo))
            if (i + 1) % 10 == 0 or i == len(registros_filtrados) - 1:
                print(f"   Progreso: {i + 1}/{len(registros_filtrados)}")

        print(f"\n[Wrangler] Validación morfológica: {len(registros_validados)} aprobados, {len(descartes_morfo)} descartados.")
        for texto, motivo in descartes_morfo:
            print(f"   DESCARTADO: {motivo} -> \"{texto}\"")

        if not registros_validados:
            print("[Wrangler] Ningún registro pasó la validación morfológica.")
            return
    else:
        registros_validados = registros_filtrados
        print("[Wrangler] Validación morfológica DESACTIVADA (VALIDACION_MORFOLOGICA=False).")

    e3, e5 = clasificar_por_estrategia(registros_validados)
    print(f"\n[Wrangler] Estrategia 3: {len(e3)} | Estrategia 5: {len(e5)}")

    pestana_e3 = conectar_a_pestana(TAB_E3, COLUMNAS_E3)
    pestana_e5 = conectar_a_pestana(TAB_E5, COLUMNAS_E5)

    if e3:
        print(f"\n[Wrangler] Subiendo {len(e3)} filas a '{TAB_E3}'...")
        try:
            n = subir_a_pestana(pestana_e3, formatear_filas_e3(e3))
            print(f"   OK - {n} filas cargadas en '{TAB_E3}'.")
        except Exception as e:
            print(f"   ERROR al subir a '{TAB_E3}': {e}")

    if e5:
        print(f"\n[Wrangler] Subiendo {len(e5)} filas a '{TAB_E5}'...")
        try:
            n = subir_a_pestana(pestana_e5, formatear_filas_e5(e5))
            print(f"   OK - {n} filas cargadas en '{TAB_E5}'.")
        except Exception as e:
            print(f"   ERROR al subir a '{TAB_E5}': {e}")

    print(f"\n[Wrangler] Moviendo archivos de raw/ a procesados/...")
    for ruta_archivo in archivos_jsonl:
        destino = os.path.join(CARPETA_PROCESADOS, os.path.basename(ruta_archivo))
        shutil.move(ruta_archivo, destino)
        print(f"   {os.path.basename(ruta_archivo)} -> procesados/")

    print("\n[OK] FASE 1 COMPLETADA.")

# ─── FASE 3: Sheets -> clasificación ───

def _parsear_puntaje(valor) -> int | None:
    if valor is None or str(valor).strip() == "":
        return None
    try:
        return int(float(str(valor).strip()))
    except (ValueError, TypeError):
        return None


def fase3_clasificar():
    print("=" * 60)
    print("FASE 3: Sheets -> clasificación (aprobado / corregido / rechazado)")
    print("=" * 60)

    asegurar_carpetas()

    aprobados = []
    dorados = []
    corregidos = []
    rechazados = []
    pendientes = 0

    for nombre_tab in [TAB_E3, TAB_E5]:
        try:
            pestana = conectar_a_pestana(nombre_tab, [], crear_si_no_existe=False)
        except gspread.exceptions.WorksheetNotFound:
            print(f"[Wrangler] Pestaña '{nombre_tab}' no existe, se saltea.")
            continue

        filas = pestana.get_all_values()
        print(f"\n[Wrangler] Leyendo '{nombre_tab}': {len(filas)} filas (incluyendo cabecera).")

        if len(filas) <= 1:
            print(f"   Sin datos para procesar.")
            continue

        cabecera = [c.strip().lower() for c in filas[0]]
        idx_correccion = cabecera.index("correccion") if "correccion" in cabecera else -1
        idx_sintaxis = cabecera.index("puntaje_sintaxis") if "puntaje_sintaxis" in cabecera else -1
        idx_semantica = cabecera.index("puntaje_semantica") if "puntaje_semantica" in cabecera else -1

        for i, fila in enumerate(filas[1:], start=2):
            if len(fila) < 2:
                continue

            registro = {"estrategia": "3" if nombre_tab == TAB_E3 else "5"}

            for j, valor in enumerate(fila):
                if j < len(cabecera):
                    registro[cabecera[j]] = valor.strip()

            correccion = fila[idx_correccion].strip() if idx_correccion >= 0 and len(fila) > idx_correccion else ""
            puntaje_sintaxis = _parsear_puntaje(fila[idx_sintaxis] if idx_sintaxis >= 0 and len(fila) > idx_sintaxis else None)
            puntaje_semantica = _parsear_puntaje(fila[idx_semantica] if idx_semantica >= 0 and len(fila) > idx_semantica else None)

            if correccion:
                registro["correccion"] = correccion
                corregidos.append(registro)
                continue

            if puntaje_sintaxis is None or puntaje_semantica is None:
                pendientes += 1
                continue

            if puntaje_sintaxis >= 4 and puntaje_semantica >= 4:
                aprobados.append(registro)
                if puntaje_sintaxis == 5 and puntaje_semantica == 5:
                    dorados.append(registro)
            else:
                registro["puntaje_sintaxis"] = puntaje_sintaxis
                registro["puntaje_semantica"] = puntaje_semantica
                rechazados.append(registro)

    print(f"\n[Wrangler] Resultado de clasificación:")
    print(f"   Aprobados:  {len(aprobados)}")
    print(f"   Corregidos: {len(corregidos)}")
    print(f"   Dorados (5/5): {len(dorados)}")
    print(f"   Rechazados: {len(rechazados)}")
    if pendientes > 0:
        print(f"   Pendientes (sin revisar): {pendientes}")

    if aprobados:
        with open(ARCHIVO_DATASET, "a", encoding="utf-8") as f:
            for reg in aprobados:
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        print(f"\n   [+] {len(aprobados)} registros agregados a '{ARCHIVO_DATASET}'.")

    if dorados:
        os.makedirs(os.path.dirname(ARCHIVO_DORADOS), exist_ok=True)
        with open(ARCHIVO_DORADOS, "w", encoding="utf-8") as f:
            for reg in dorados:
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        print(f"   [+] {len(dorados)} dorados (5/5) escritos a '{ARCHIVO_DORADOS}'.")

    if corregidos:
        os.makedirs(os.path.dirname(ARCHIVO_PARA_REGENERAR), exist_ok=True)
        with open(ARCHIVO_PARA_REGENERAR, "w", encoding="utf-8") as f:
            for reg in corregidos:
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        print(f"   [+] {len(corregidos)} registros escritos a '{ARCHIVO_PARA_REGENERAR}'.")

    if rechazados:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        ruta_rechazo = os.path.join(CARPETA_RECHAZADOS, f"rechazados_{ts}.jsonl")
        with open(ruta_rechazo, "w", encoding="utf-8") as f:
            for reg in rechazados:
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        print(f"   [+] {len(rechazados)} registros escritos a '{ruta_rechazo}'.")

    print("\n[OK] FASE 3 COMPLETADA.")

# ─── MAIN ───

def main():
    import sys
    asegurar_carpetas()

    if len(sys.argv) > 1:
        fase = sys.argv[1]
    else:
        print("Ejecutar FASE 1 (subir) o FASE 3 (clasificar)?")
        print("  1 - FASE 1: raw/ -> Sheets (validación + carga)")
        print("  3 - FASE 3: Sheets -> archivos locales (clasificación)")
        fase = input("> ").strip()

    if fase == "1":
        fase1_subir()
    elif fase == "3":
        fase3_clasificar()
    else:
        print(f"Fase '{fase}' no reconocida. Usá: python data_wrangler.py 1  o  python data_wrangler.py 3")


if __name__ == "__main__":
    main()
