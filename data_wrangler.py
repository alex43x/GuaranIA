"""
DATA WRANGLER — Pipeline completo de filtrado, validación y carga a Google Sheets
==================================================================================
FASE 1: raw/ -> análisis LLM -> Sheets (pestañas estrategia_3 / estrategia_5)
FASE 3: Sheets -> clasificación -> dataset_acumulado_estrategia{3,5}.jsonl / feedback / rechazados

Requisitos: pip install gspread google-auth gradio_client requests
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
def _ruta_acumulado(estrategia: str) -> str:
    return f"dataset_acumulado_estrategia{estrategia}.jsonl"

def _ruta_dorados(estrategia: str) -> str:
    return f"feedback/estrategia{estrategia}/dorados.jsonl"

def _ruta_para_regenerar_grupo(estrategia: str, seed_file: str, dominio: str, ts: str) -> str:
    seed_nombre = os.path.splitext(os.path.basename(seed_file))[0] if seed_file else "sin_seed"
    carpeta = f"feedback/estrategia{estrategia}"
    os.makedirs(carpeta, exist_ok=True)
    return f"{carpeta}/para_regenerar_{seed_nombre}_{dominio}_{ts}.jsonl"

CAMPOS_REQUERIDOS = ["texto", "texto_base", "tipo_transformacion", "dominio", "estrategia"]
COLUMNAS_E3 = ["texto", "texto_base", "tipo_transformacion", "dominio", "estrategia",
               "puntaje_sintaxis", "puntaje_semantica", "correccion", "tipo_error", "posibles_errores"]
COLUMNAS_E5 = ["texto", "dominio", "estrategia", "prompt",
               "puntaje_sintaxis", "puntaje_semantica", "correccion", "tipo_error",
               "posibles_errores", "seed_file"]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

VALIDACION_MORFOLOGICA = False  # Cambiar a cuando se quiera aplicar API externa para correciones con morfologia
ANALIZAR_ERRORES_LLM = True     # Analizar oraciones con LLM local antes de subir al Sheet

# ─── HELPERS ───

def asegurar_carpetas():
    for carpeta in [CARPETA_RAW, CARPETA_PROCESADOS, CARPETA_RECHAZADOS,
                    CARPETA_FEEDBACK, CARPETA_BACKUPS]:
        os.makedirs(carpeta, exist_ok=True)


def backup_raw():
    archivos = glob.glob(os.path.join(CARPETA_RAW, "*.jsonl"))
    if not archivos:
        return
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
        else:
            faltantes = [c for c in columnas if c not in primera_fila]
            if faltantes:
                for col in faltantes:
                    pestana.update_cell(1, len(primera_fila) + 1, col)
                    primera_fila.append(col)
                print(f"   Pestaña '{nombre_pestana}': columnas agregadas: {faltantes}")
        return pestana
    except gspread.exceptions.WorksheetNotFound:
        if crear_si_no_existe:
            pestana = hoja.add_worksheet(title=nombre_pestana, rows="1000", cols="12")
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
    textos_aprobados = set()
    for estrategia in ["3", "5"]:
        ruta = _ruta_acumulado(estrategia)
        if not os.path.exists(ruta):
            continue
        with open(ruta, "r", encoding="utf-8", errors="replace") as f:
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
            "", "", "", "",
            reg.get("posibles_errores", ""),
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
            "", "", "", "",
            reg.get("posibles_errores", ""),
            reg.get("seed_file", ""),
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
        with open(ruta_archivo, "r", encoding="utf-8", errors="replace") as f:
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

    if ANALIZAR_ERRORES_LLM:
        from analizador_errores import analizar_oracion, parsear_respuesta, conectar_llm
        print(f"\n[Wrangler] Analizando errores con LLM local ({len(registros_validados)} registros)...")
        conectar_llm()
        import time as _time
        errores_encontrados = 0
        for i, reg in enumerate(registros_validados):
            texto = reg.get("texto", "")
            try:
                respuesta = analizar_oracion(texto)
                errores = parsear_respuesta(respuesta)
                errores = errores.strip().replace('\n', ' | ').replace('\\n', ' | ')
                if len(errores) > 300:
                    errores = errores[:297] + '...'
                reg["posibles_errores"] = errores
                if errores and errores != "sin errores":
                    errores_encontrados += 1
            except Exception as e:
                reg["posibles_errores"] = f"ERROR_API: {e}"
            if (i + 1) % 5 == 0 or i == len(registros_validados) - 1:
                print(f"   Progreso: {i + 1}/{len(registros_validados)}")
            _time.sleep(1)
        print(f"[Wrangler] Análisis LLM completado: {errores_encontrados}/{len(registros_validados)} con errores detectados.")

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


def _filtar_registro_export(reg: dict) -> dict:
    return {
        "texto": reg.get("texto", ""),
        "dominio": reg.get("dominio", ""),
        "prompt": reg.get("prompt", ""),
        "seed_file": reg.get("seed_file", ""),
    }


def fase3_clasificar(dry_run: bool = False):
    print("=" * 60)
    modo = " (DRY RUN)" if dry_run else ""
    print(f"FASE 3: Sheets -> clasificación (acumulado / para_regenerar){modo}")
    print("=" * 60)

    asegurar_carpetas()

    aprobados = []
    dorados = []
    por_regenerar = {}  # (seed_file, dominio) -> list[dict]
    pendientes = 0
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    nombre_tab = TAB_E5
    try:
        pestana = conectar_a_pestana(nombre_tab, [], crear_si_no_existe=False)
    except gspread.exceptions.WorksheetNotFound:
        print(f"[Wrangler] Pestaña '{nombre_tab}' no existe.")
        return

    filas = pestana.get_all_values()
    print(f"\n[Wrangler] Leyendo '{nombre_tab}': {len(filas)} filas (incluyendo cabecera).")

    if len(filas) <= 1:
        print(f"   Sin datos para procesar.")
        return

    cabecera = [c.strip().lower() for c in filas[0]]
    idx_correccion = cabecera.index("correccion") if "correccion" in cabecera else -1
    idx_sintaxis = cabecera.index("puntaje_sintaxis") if "puntaje_sintaxis" in cabecera else -1
    idx_semantica = cabecera.index("puntaje_semantica") if "puntaje_semantica" in cabecera else -1
    idx_tipo_error = cabecera.index("tipo_error") if "tipo_error" in cabecera else -1

    for i, fila in enumerate(filas[1:], start=2):
        if len(fila) < 2:
            continue

        registro = {}
        for j, valor in enumerate(fila):
            if j < len(cabecera):
                registro[cabecera[j]] = valor.strip()

        seed_file = registro.get("seed_file", "")
        dominio = registro.get("dominio", "sin_dominio")
        prompt = registro.get("prompt", "")

        correccion = fila[idx_correccion].strip() if idx_correccion >= 0 and len(fila) > idx_correccion else ""
        tipo_error = fila[idx_tipo_error].strip() if idx_tipo_error >= 0 and len(fila) > idx_tipo_error else ""
        puntaje_sintaxis = _parsear_puntaje(fila[idx_sintaxis] if idx_sintaxis >= 0 and len(fila) > idx_sintaxis else None)
        puntaje_semantica = _parsear_puntaje(fila[idx_semantica] if idx_semantica >= 0 and len(fila) > idx_semantica else None)

        if correccion:
            registro["correccion"] = correccion
            if tipo_error:
                registro["tipo_error"] = tipo_error
            key = (seed_file, dominio)
            if key not in por_regenerar:
                por_regenerar[key] = {"oraciones": [], "prompt": prompt}
            por_regenerar[key]["oraciones"].append(registro)
            continue

        if puntaje_sintaxis is None or puntaje_semantica is None:
            pendientes += 1
            continue

        if puntaje_sintaxis == 5 and puntaje_semantica == 5:
            registro["puntaje_sintaxis"] = puntaje_sintaxis
            registro["puntaje_semantica"] = puntaje_semantica
            aprobados.append(registro)
            dorados.append(registro)
        else:
            registro["puntaje_sintaxis"] = puntaje_sintaxis
            registro["puntaje_semantica"] = puntaje_semantica
            if tipo_error:
                registro["tipo_error"] = tipo_error
            key = (seed_file, dominio)
            if key not in por_regenerar:
                por_regenerar[key] = {"oraciones": [], "prompt": prompt}
            por_regenerar[key]["oraciones"].append(registro)

    print(f"\n[Wrangler] Resultado de clasificación:")
    print(f"   Aprobados (5/5):  {len(aprobados)}")
    print(f"   Dorados (5/5):    {len(dorados)}")
    total_para_regenerar = sum(len(g["oraciones"]) for g in por_regenerar.values())
    print(f"   Para regenerar:   {total_para_regenerar} (en {len(por_regenerar)} grupos)")
    if pendientes > 0:
        print(f"   Pendientes (sin revisar): {pendientes}")

    if aprobados:
        ruta = _ruta_acumulado("5")
        if dry_run:
            print(f"   [+] {len(aprobados)} aprobados -> '{ruta}' (no escrito)")
        else:
            with open(ruta, "a", encoding="utf-8") as f:
                for reg in aprobados:
                    f.write(json.dumps(_filtar_registro_export(reg), ensure_ascii=False) + "\n")
            print(f"   [+] {len(aprobados)} aprobados -> '{ruta}'.")

    if dorados:
        ruta = _ruta_dorados("5")
        if dry_run:
            print(f"   [+] {len(dorados)} dorados -> '{ruta}' (no escrito)")
        else:
            os.makedirs(os.path.dirname(ruta), exist_ok=True)
            with open(ruta, "w", encoding="utf-8") as f:
                for reg in dorados:
                    f.write(json.dumps(_filtar_registro_export(reg), ensure_ascii=False) + "\n")
            print(f"   [+] {len(dorados)} dorados -> '{ruta}'.")

    for (seed_file, dominio), grupo in por_regenerar.items():
        ruta = _ruta_para_regenerar_grupo("5", seed_file, dominio, ts)
        salida = {
            "seed_file": seed_file,
            "dominio": dominio,
            "prompt": grupo.get("prompt", ""),
            "total": len(grupo["oraciones"]),
            "oraciones": [
                {
                    "texto": reg.get("texto", ""),
                    "correccion": reg.get("correccion", ""),
                    "tipo_error": reg.get("tipo_error", ""),
                }
                for reg in grupo["oraciones"]
            ],
        }
        if dry_run:
            print(f"   [+] {len(grupo['oraciones'])} para regenerar ({seed_file}/{dominio}) -> '{ruta}' (no escrito)")
        else:
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(json.dumps(salida, ensure_ascii=False) + "\n")
            print(f"   [+] {len(grupo['oraciones'])} para regenerar ({seed_file}/{dominio}) -> '{ruta}'.")

    print("\n[OK] FASE 3 COMPLETADA.")

# ─── LIMPIEZA DE posibles_errores EN EL SHEET ───

SANITIZAR_ERRORES_MAX_LEN = 300

def _sanitizar_errores(texto: str) -> str:
    t = texto.strip()
    if '"errores"' in t:
        try:
            data = json.loads(t)
            t = data.get("errores", t)
        except (json.JSONDecodeError, KeyError):
            inicio = t.find('"errores": "')
            if inicio != -1:
                t = t[inicio + len('"errores": "'):]
                fin = t.rfind('"}')
                if fin != -1:
                    t = t[:fin]
    t = t.replace("\\'", "'").replace("\\n", " | ").replace('\\"', '"')
    t = t.replace('\n', ' | ')
    if len(t) > SANITIZAR_ERRORES_MAX_LEN:
        t = t[:SANITIZAR_ERRORES_MAX_LEN - 3] + '...'
    return t.strip()


def limpiar_sheet():
    print("=" * 60)
    print("LIMPIEZA: sanitizando columna 'posibles_errores' en el Sheet")
    print("=" * 60)

    limpiadas = 0
    for nombre_tab in [TAB_E3, TAB_E5]:
        try:
            pestana = conectar_a_pestana(nombre_tab, [], crear_si_no_existe=False)
        except gspread.exceptions.WorksheetNotFound:
            continue

        cabecera = pestana.row_values(1)
        if "posibles_errores" not in cabecera:
            print(f"   [!] '{nombre_tab}' no tiene columna 'posibles_errores'.")
            continue

        idx = cabecera.index("posibles_errores")
        print(f"   '{nombre_tab}': sanitizando...")
        filas = pestana.get_all_values()

        for i, fila in enumerate(filas[1:], start=2):
            if len(fila) <= idx:
                continue
            original = fila[idx]
            if not original:
                continue
            limpio = _sanitizar_errores(original)
            if limpio != original:
                pestana.update_cell(i, idx + 1, limpio)
                limpiadas += 1

    print(f"   Celdas sanitizadas: {limpiadas}")
    print("[OK] LIMPIEZA COMPLETADA.")


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
        print("  4 - LIMPIEZA: sanitizar columna 'posibles_errores'")
        fase = input("> ").strip()

    if fase == "1":
        fase1_subir()
    elif fase == "3":
        dry = "--dry-run" in sys.argv
        fase3_clasificar(dry_run=dry)
    elif fase == "4":
        limpiar_sheet()
    else:
        print(f"Fase '{fase}' no reconocida. Usá: python data_wrangler.py 1  o  python data_wrangler.py 3")


if __name__ == "__main__":
    main()
