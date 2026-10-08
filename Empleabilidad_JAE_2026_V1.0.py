import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from google.cloud import bigquery
import dotenv 
from dotenv import load_dotenv
import os

load_dotenv()
load_dotenv(override=True)
SEGUIMIENTO_JAE = os.getenv("Sheets_JAE")

PROJECT_ID = os.getenv("PROJECT_ID")
DATASET_ID = "EFE_2026"
TABLE_ID   = "JAE_2026_Empleabilidad"

Credentials_File = "credenciales.json"

scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file(Credentials_File, scopes=scopes)
client_sheets = gspread.authorize(creds)

sheet = client_sheets.open_by_key(SEGUIMIENTO_JAE)
Hoja_Empleabilidad = sheet.worksheet("Empleabilidad")
Datos = Hoja_Empleabilidad.get_all_values()
DF = pd.DataFrame(Datos[1:], columns=Datos[0])
Headers = DF.columns
DF = DF.loc[:, DF.columns != ""]

DF = DF.replace(r'^\s*$', None, regex=True)
DF = DF.where(pd.notnull(DF), None)

DF = DF.dropna(subset=['Documento'])

DF.columns = (DF.columns
              .str.replace(" ","_")
              .str.normalize('NFKD')
              .str.encode('ascii', errors='ignore')
              .str.decode('utf-8')
              .str.lower()
              .str.replace(r"[\r\n]+", "", regex=True)
              .str.replace(r"[^a-z0-9_#]", "", regex=True)              
              )
DF = DF.loc[:, ~DF.columns.duplicated()]
DF = DF.iloc[:, 0:26]

Columnas_int_float = []
for columna in DF.columns:
    if columna == 'postulaciones_realizadas' or columna == '#_descartados':
        Columnas_int_float.append(columna)

DF[Columnas_int_float].apply(pd.to_numeric, errors='coerce').astype("Int64")

DF['proyecto'] = "Jóvenes a la E"

print(DF.columns.to_list())

client_bq = bigquery.Client.from_service_account_json(Credentials_File)

table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

from validacion_dataframes import validar_y_comparar
validar_y_comparar(Hoja_Empleabilidad.title, DF, client_bq, table_ref)

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