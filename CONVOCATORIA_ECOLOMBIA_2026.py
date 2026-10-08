import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from google.cloud import bigquery
import dotenv 
from dotenv import load_dotenv
import os

load_dotenv()
load_dotenv(override=True)
CONVOCATORIA_ECO = os.getenv("Sheets_Convocatoria_ECO")

PROJECT_ID = os.getenv("PROJECT_ID")
DATASET_ID = "EFE_2026"
TABLE_ID   =  "ECOPLUS_2026_CONVOCATORIA"

Credentials_File = "credenciales.json"

scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file(Credentials_File, scopes=scopes)
client_sheets = gspread.authorize(creds)

sheet = client_sheets.open_by_key(CONVOCATORIA_ECO)

Hoja_convocatoria = sheet.worksheet("SEGUIMIENTO FASE 1")
Datos = Hoja_convocatoria.get_all_values()
DF = pd.DataFrame(Datos[1:], columns=Datos[0])
Headers = DF.columns
DF = DF.loc[:, DF.columns != ""]
DF = DF.replace(r'^\s*$', None, regex=True)
DF = DF.where(pd.notnull(DF), None)

DF = DF.dropna(subset=['Número de Documento'])

DF.columns = (DF.columns
              .str.replace(" ","_")
              .str.normalize('NFKD')
              .str.encode('ascii', errors='ignore')
              .str.decode('utf-8')
              .str.lower()
              .str.replace(r"[\r\n]+", "", regex=True)
              .str.replace(r"[^a-z0-9_#]", "", regex=True)              
              )

Col_string_to_date = []
for columnas_fecha in DF.columns:
    if 'fecha' in columnas_fecha:
        Col_string_to_date.append(columnas_fecha)
        DF[columnas_fecha] = pd.to_datetime(DF[columnas_fecha], dayfirst=True, errors='coerce') 

DF = DF.iloc[:, 0:54]
DF['proyecto'] = "Ecolombia 2.0"

print(DF.columns.to_list())

client_bq = bigquery.Client.from_service_account_json(Credentials_File)
table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

from validacion_dataframes import validar_y_comparar
validar_y_comparar(Hoja_convocatoria.title, DF, client_bq, table_ref)

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