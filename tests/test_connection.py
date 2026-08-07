"""
TEST DE CONEXIÓN — solo para confirmar que Google Sheets responde
====================================================================
No limpia, no valida, no hace nada del pipeline real.
Sube 2 filas de prueba y las vuelve a leer, para confirmar que
credenciales.json y los permisos de la hoja están bien configurados.

Requisitos: pip install gspread google-auth --break-system-packages
Antes de correr, editá las dos variables de abajo con el nombre
real de tu hoja y de la pestaña.
"""

import gspread
from google.oauth2.service_account import Credentials

# ─── EDITÁ ESTO ───
NOMBRE_HOJA = "hackathon-test"
NOMBRE_PESTANA = "para_validar"
# ──────────────────

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def main():
    print("1. Autenticando con credenciales.json...")
    try:
        creds = Credentials.from_service_account_file("./credenciales.json", scopes=SCOPES)
        cliente = gspread.authorize(creds)
        print("   OK — credenciales leídas y autenticación aceptada.\n")
    except FileNotFoundError:
        print("   ERROR: no encuentro 'credenciales.json' en esta carpeta.")
        return
    except Exception as e:
        print(f"   ERROR al autenticar: {e}")
        return

    print(f"2. Abriendo la hoja '{NOMBRE_HOJA}'...")
    try:
        hoja = cliente.open(NOMBRE_HOJA)
        print("   OK — la hoja existe y la cuenta de servicio tiene acceso.\n")
    except gspread.exceptions.SpreadsheetNotFound:
        print("   ERROR: no encuentro esa hoja. Revisá:")
        print("   - ¿El nombre está escrito exactamente igual que en Google Sheets?")
        print("   - ¿Compartiste la hoja con el email de la cuenta de servicio")
        print("     (el que termina en ...iam.gserviceaccount.com, del JSON)?")
        return

    print(f"3. Abriendo la pestaña '{NOMBRE_PESTANA}'...")
    try:
        pestana = hoja.worksheet(NOMBRE_PESTANA)
        print("   OK — la pestaña existe.\n")
    except gspread.exceptions.WorksheetNotFound:
        print(f"   ERROR: no existe una pestaña llamada '{NOMBRE_PESTANA}' en esa hoja.")
        print("   Creala en Google Sheets o corregí el nombre acá arriba.")
        return

    print("4. Escribiendo una fila de prueba...")
    pestana.update([["texto_prueba", "conexion_ok"], ["Mba'éichapa nde", "HOLAAA SOY FHFHJFs"]])
    print("   OK — escrita.\n")

    print("5. Releyendo lo que acabo de escribir...")
    valores = pestana.get_all_values()
    print("   Contenido actual de la pestaña:")
    for fila in valores:
        print("   ", fila)

    print("\n✅ CONEXIÓN CONFIRMADA — todo funciona de punta a punta.")
    print("Fijate en Sheets (navegador) si 'Mba'éichapa nde' se ve bien,")
    print("sin símbolos raros en el apóstrofe o los acentos.")


if __name__ == "__main__":
    main()