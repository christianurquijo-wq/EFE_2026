import pandas as pd
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore

# Rutas relativas a esta carpeta: funciona igual desde VS Code, el lote o GitHub Actions.
BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE, ".env"), override=True)

# Proyecto de Firebase a comparar: firebase_credentials_a.json (el mismo que usa main.py) por defecto.
# Para otro: FIREBASE_CRED=firebase_credentials_b.json en el .env de esta carpeta.
cred_firebase = credentials.Certificate(os.path.join(BASE, os.getenv("FIREBASE_CRED", "firebase_credentials_a.json")))
firebase_admin.initialize_app(cred_firebase)
db_fs = firestore.client()

db = os.getenv("db")
json_sheets = os.path.join(BASE, "applied-plexus-476714-n0-d7c1f0400cc6.json")
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
cred_sheets = ServiceAccountCredentials.from_json_keyfile_name(json_sheets, scope)
client = gspread.authorize(cred_sheets)

print("1. Descargando datos de Google Sheets...")
documento = client.open_by_key(db)
hoja = documento.worksheet("Hoja 1")
datos = hoja.get_all_values()
df_excel = pd.DataFrame(datos[1:], columns=datos[0])

correos_excel = []
for index, row in df_excel.iterrows():
    correo = str(row.get("Correo", "")).lower().strip()
    if correo and "@" in correo:
        correos_excel.append(correo)

print("2. Descargando datos de Firebase...")
docs_firebase = db_fs.collection("usuarios_permitidos").stream()
correos_firebase = [doc.id for doc in docs_firebase]

df_sheets_clean = pd.DataFrame(correos_excel, columns=["Correo_Excel"])
df_firebase_clean = pd.DataFrame(correos_firebase, columns=["Correo_Firebase"])

print("\n================ RESUMEN ==================")
print(f"Total correos válidos leídos en Excel: {len(correos_excel)}")
print(f"Total documentos creados en Firebase: {len(correos_firebase)}")
print("===========================================")

duplicados = df_sheets_clean[df_sheets_clean.duplicated(['Correo_Excel'], keep=False)]
if not duplicados.empty:
    print(f"\n⚠️ SE ENCONTRARON {len(duplicados['Correo_Excel'].unique())} CORREOS DUPLICADOS EN EL EXCEL:")
    for correo in duplicados['Correo_Excel'].unique():
        cantidad = len(df_sheets_clean[df_sheets_clean['Correo_Excel'] == correo])
        print(f"  - {correo} (Aparece {cantidad} veces)")

set_excel = set(correos_excel)
set_firebase = set(correos_firebase)

faltan_en_firebase = set_excel - set_firebase

if faltan_en_firebase:
    print(f"\n❌ CORREOS EN EL EXCEL QUE NO SUBIERON A FIREBASE ({len(faltan_en_firebase)}):")
    for c in faltan_en_firebase:
        print(f"  - {c}")
else:
    print("\n✅ Todos los correos únicos del Excel están subidos a Firebase.")