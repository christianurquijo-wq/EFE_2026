import pandas as pd
from google.cloud import bigquery
import os
from dotenv import load_dotenv
import pydrive2
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from io import StringIO
from google.cloud.exceptions import NotFound

load_dotenv(override=True)
Credenciales = 'credenciales.json'
client_bq = bigquery.Client.from_service_account_json(Credenciales)
credentials_drive = "credentials_module.json"

def loggin_drive():
    gauth = GoogleAuth()
    gauth.LoadCredentialsFile(credentials_drive)

    if gauth.access_token_expired:
        gauth.Refresh() 
        gauth.SaveCredentialsFile(credentials_drive)
    else:
        gauth.Authorize()
    
    return GoogleDrive(gauth)
    
drive = loggin_drive()

PROJECT_ID = os.getenv("PROJECT_ID")
DATA_SET = os.getenv("DATA_SET")
Dataset_ID = f"{PROJECT_ID}.{DATA_SET}"

configuraciones_backup = [
    {
        "filtro": "APPEND", 
        "folder_id": os.getenv("folder_id_backup")
    },
    {
        "filtro": "RECUPERACIONES", 
        "folder_id": os.getenv("folder_id_backup_recuperaciones")
    }
]

Lista_tablas = list(client_bq.list_tables(Dataset_ID))

for config in configuraciones_backup:
    filtro = config["filtro"]
    folder_id = config["folder_id"]

    query_drive = f"'{folder_id}' in parents and trashed = false"
    Lista_archivos_drive = drive.ListFile({'q': query_drive}).GetList()

    Lista_drive_backup = []
    for archivos_carpetas in Lista_archivos_drive:
        nombre_archivo = archivos_carpetas['title']
        id_archivo = archivos_carpetas['id']
        Lista_drive_backup.append({'Nombre': nombre_archivo, 'ID': id_archivo})

    for tabla in Lista_tablas:
        if filtro in tabla.table_id:
            nombre_tabla = tabla.table_id
            query = f"SELECT * FROM `{Dataset_ID}.{nombre_tabla}`"
            tabla_backup = client_bq.query(query).to_dataframe()
            tabla_backup = pd.DataFrame(tabla_backup)
            nombre_csv = f"{nombre_tabla}.csv"
            
            validacion_existente = next((item['ID'] for item in Lista_drive_backup if item['Nombre'] == nombre_csv), None)
            
            if validacion_existente:
                file_drive = drive.CreateFile({'id': validacion_existente})
                Backup = "Actualizado"
            else:
                file_drive = drive.CreateFile({
                    'title': f"{nombre_tabla}.csv",
                    'parents': [{'id': folder_id}],
                    'mimeType': 'text/csv'
                })
                Backup = "Generado" 
                
            tabla_csv = tabla_backup.to_csv(index=False, encoding="utf-8")
            file_drive.SetContentString(tabla_csv)
            file_drive.Upload()
            print(f"Backup de {nombre_tabla} {Backup} exitosamente")

    for csv in Lista_archivos_drive:
        if filtro in csv['title']:
            tabla_nombre = csv['title'].replace('.csv', '')
            tabla_id = f"{Dataset_ID}.{tabla_nombre}"

            try:
                client_bq.get_table(tabla_id)
                print(f"La tabla {tabla_nombre} todavía no se vence en Bigquery")
            except NotFound:
                print(f"Tabla '{tabla_id}' expirada. Restaurando desde el Backup")
                archivo_id_drive = drive.CreateFile({'id': csv['id']})
                archivo_drive_ram = archivo_id_drive.GetContentString()  
                tabla_to_upload = pd.read_csv(StringIO(archivo_drive_ram))

                job = client_bq.load_table_from_dataframe(
                    tabla_to_upload,
                    tabla_id,
                    job_config=bigquery.LoadJobConfig(
                        write_disposition="WRITE_TRUNCATE",
                        autodetect=True
                    )
                )
                job.result()
                print(f"Verificada la restauración de {tabla_nombre}")

print("Total Backups Generados y Verificados")