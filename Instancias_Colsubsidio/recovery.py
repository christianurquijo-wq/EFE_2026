import pandas as pd
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore

load_dotenv(override=True)

cred_firebase = credentials.Certificate(r"firebase_credentials_c.json")
firebase_admin.initialize_app(cred_firebase)
db_fs = firestore.client()

db = os.getenv("db_recovery")

json_sheets = "applied-plexus-476714-n0-d7c1f0400cc6.json"
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
cred_sheets = ServiceAccountCredentials.from_json_keyfile_name(json_sheets, scope)
client = gspread.authorize(cred_sheets)

documento = client.open_by_key(db)
hoja = documento.worksheet("Hoja 1")
datos = hoja.get_all_values()

df = pd.DataFrame(datos[1:], columns=datos[0])

print(df.columns)

df.columns = df.columns.str.strip().str.replace('"', '')

print(df)

batch = db_fs.batch()
contador = 0

for index, row in df.iterrows():
    correo_crudo = str(row.get('correo', '')).strip().replace('"', '').lower()
    
    if not correo_crudo or correo_crudo == 'nan' or correo_crudo == '':
        continue

    datos_dict = row.to_dict()
    print(datos_dict)
    
    if 'Document ID' in datos_dict:
        del datos_dict['Document ID']
        
    datos_limpios = {}
    for k, v in datos_dict.items():
        if pd.notna(v):
            valor_limpio = str(v).strip().replace('"', '')
            if valor_limpio != "":
                clave_limpia = str(k).strip().replace('"', '')
                datos_limpios[clave_limpia] = valor_limpio

    doc_ref = db_fs.collection("respuestas").document(correo_crudo)
    batch.set(doc_ref, datos_limpios)
    
    contador += 1
    if contador % 400 == 0:
        batch.commit()
        batch = db_fs.batch()

if contador % 400 != 0:
    batch.commit()

print(f"Proceso finalizado. {contador} respuestas migradas.")