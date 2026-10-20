import pandas as pd
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore

load_dotenv(override=True)

cred_firebase = credentials.Certificate(r"firebase_credentials_a.json")
firebase_admin.initialize_app(cred_firebase)
db_fs = firestore.client()

db = os.getenv("db")
json_sheets = "applied-plexus-476714-n0-d7c1f0400cc6.json"
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
cred_sheets = ServiceAccountCredentials.from_json_keyfile_name(json_sheets, scope)
client = gspread.authorize(cred_sheets)

correos_docentes = {
    "Sandra Isabel Rodriguez": "sandra.rodriguez1@kuepa.edu.co",
    "Steven Salazar": "steven.salazar@kuepa.edu.co",
    "Cheryl Vasquez": "cheryl.vasquez@kuepa.edu.co",
    "Sebastian Rojas": "sebastian.rojas@kuepa.edu.co",
    "Nestor Raul Ospina": "nestor.ospina@kuepa.edu.co",
    "Carol Julieth Zambrano Gomez": "carol.zambrano@kuepa.edu.co",
    "Laura Perez Bellon": "laura.perezb@kuepa.edu.co",
    "Camilo Castillo": "camilo.castillo@kuepa.edu.co",
    "David Berdugo": "david.berdugo@kuepa.edu.co",
    "Victor Leonardo Bellon": "victor.bellon@kuepa.edu.co",
    "Sonia Martinez": "sonia.martinez@kuepa.edu.co",
    "Elder Rivero": "elder.rivero@kuepa.edu.co"
}

mapa_grupos_tutor = {
    "T2.0C6G46": "Carol Julieth Zambrano Gomez",
    "T2.0C6G47": "Camilo Castillo",
    "T2.0C6G48": "Sebastian Rojas",
    "T2.0C6G49": "Sebastian Rojas",
    "T2.0C6G50": "Steven Salazar",
    "T2.0C6G51": "Steven Salazar",
    "T2.0C6G52": "Sonia Martinez",
    "T2.0C6G53": "David Berdugo",
    "T2.0C6G54": "David Berdugo",
    "T2.0C6G55": "Sandra Isabel Rodriguez",
    "T2.0C6G56": "Sandra Isabel Rodriguez",
    "T2.0C6G57": "Laura Perez Bellon",
    "T2.0C6G58": "Laura Perez Bellon",
    "T2.0C6G59": "Elder Rivero",
    "T2.0C6G60": "Cheryl Vasquez",
    "T2.0C6G61": "Nestor Raul Ospina",
    "T2.0C6G62": "Nestor Raul Ospina",
    "T2.0C6G63": "Victor Leonardo Bellon",
    "T2.0C6G64": "Carol Julieth Zambrano Gomez"
}

grupos_por_tutor = {}
for grupo, tutor in mapa_grupos_tutor.items():
    if tutor not in grupos_por_tutor:
        grupos_por_tutor[tutor] = []
    grupos_por_tutor[tutor].append(grupo)

print("Descargando datos de Google Sheets...")
documento = client.open_by_key(db)
hoja = documento.worksheet("Hoja 1")
datos = hoja.get_all_values()
df = pd.DataFrame(datos[1:], columns=datos[0])
df.columns = df.columns.str.strip()

print("Subiendo Profesores a Firebase...")
for nombre_tutor, lista_grupos in grupos_por_tutor.items():
    correo_admin = correos_docentes.get(nombre_tutor)
    if correo_admin:
        ref = db_fs.collection("administradores").document(correo_admin)
        ref.set({
            "nombre": nombre_tutor,
            "clave": correo_admin,
            "grupos": lista_grupos
        })
        print(f"  -> Creado profe: {nombre_tutor} con {len(lista_grupos)} grupo(s).")

print("\nSubiendo estudiantes a Firebase...")
batch = db_fs.batch()
counter = 0

for index, row in df.iterrows():
    correo_est = str(row.get("Correo", "")).lower().strip()
    
    if not correo_est or "@" not in correo_est:
        continue
        
    codigo_excel = str(row.get("Codigo grupo", "")).strip()
    tutor_asignado = ""
    codigo_limpio = ""
    
    for codigo_corto, tutor in mapa_grupos_tutor.items():
        if codigo_corto in codigo_excel:
            tutor_asignado = tutor
            codigo_limpio = codigo_corto
            break
            
    if not codigo_limpio:
        codigo_limpio = codigo_excel
        
    doc_ref = db_fs.collection("usuarios_permitidos").document(correo_est)
    batch.set(doc_ref, {
        "correo": correo_est,
        "curso": row.get("Curso de formacion", ""),
        "codigo_grupo": codigo_limpio,
        "documento": row.get("Numero de documento", ""),
        "nombre": row.get("Nombres y apellidos"),
        "tutor": tutor_asignado
    })
    
    counter += 1
    if counter % 400 == 0:
        batch.commit()
        batch = db_fs.batch()

if counter % 400 != 0:
    batch.commit()
    
print(f"¡Proceso finalizado! {counter} estudiantes autorizados exitosamente.")