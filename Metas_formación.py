import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from google.cloud import bigquery
import dotenv 
from dotenv import load_dotenv
import os

load_dotenv(override=True)
DATA_LOOKER = os.getenv("Data_looker_suba")

PROJECT_ID = os.getenv("PROJECT_ID")
DATASET_ID = "EFE_2026"
TABLE_ID   = "SUBA_2026_METAS_FORMACION"

Credentials_File = "credenciales.json"

scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file(Credentials_File, scopes=scopes)
client_sheets = gspread.authorize(creds)

sheet = client_sheets.open_by_key(DATA_LOOKER)
Hoja_metas = sheet.worksheet('Parámetros')
Datos = Hoja_metas.get_all_values()
DF = pd.DataFrame(Datos[2:], columns=Datos[1])
DF = DF.iloc[:, 2:8]

DF.columns = (DF.columns
              .str.replace(" ","_")
              .str.normalize('NFKD')
              .str.encode('ascii', errors='ignore')
              .str.decode('utf-8')
              .str.lower()
              .str.replace(r"[\r\n]+", "", regex=True)
              .str.replace(r"[^a-z0-9_#]", "", regex=True)              
              )

columnas_numericas = ['cantidad', 'formados', 'en_curso']
DF[columnas_numericas] = DF[columnas_numericas].astype("Int64")
DF['#mes'] = pd.to_datetime(DF['#mes'].apply(lambda x: f"{x}, '-','2026'")).dt.strftime('%m-%Y')

print(DF.columns.to_list())

client_bq = bigquery.Client.from_service_account_json(Credentials_File)
table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

from validacion_dataframes import validar_y_comparar

print("Iniciando control de calidad de columnas")
validar_y_comparar(sheet.title, DF, client_bq, table_ref)

job = client_bq.load_table_from_dataframe(
    DF,
    table_ref,
    job_config=bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
        autodetect=True
    )
)

job.result()
print("Verificado")