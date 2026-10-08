import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from google.cloud import bigquery
import dotenv 
from dotenv import load_dotenv
import os

load_dotenv()
load_dotenv(override=True)
Satisfaccion_suba = os.getenv("Sheets_Satisfaccion_Suba")
PROJECT_ID = os.getenv("PROJECT_ID")
DATASET_ID = os.getenv("DATA_SET")
TABLE_ID   =  "Suba_2026_Satisfaccion"

Credentials_File = "credenciales.json"

scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file(Credentials_File, scopes=scopes)
client_sheets = gspread.authorize(creds)

sheet = client_sheets.open_by_key(Satisfaccion_suba)
print(sheet)

Hoja_satisfaccion = sheet.worksheet("Hoja 1")
Datos = Hoja_satisfaccion.get_all_values()
DF = pd.DataFrame(Datos[2:], columns=Datos[1])
Headers = DF.columns
DF = DF.loc[:, DF.columns != ""]
DF = DF.replace(r'^\s*$', None, regex=True)
DF = DF.where(pd.notnull(DF), None)

DF = DF.dropna(subset=['Número de documento.'])

DF.columns = (DF.columns
              .str.replace(" ","_")
              .str.normalize('NFKD')
              .str.encode('ascii', errors='ignore')
              .str.decode('utf-8')
              .str.lower()
              .str.replace(r"[\r\n]+", "", regex=True)
              .str.replace(r"[^a-z0-9_#]", "", regex=True)              
              )

columna_larga = DF.columns[DF.columns.str.contains('autorizo', case=False)][0]
DF = DF.rename(columns={columna_larga: 'autorizacion_datos'})

DF = DF.loc[:, ~DF.columns.duplicated()]
DF['proyecto'] = 'Suba es Oportunidad'

print(DF.columns.to_list())

client_bq = bigquery.Client.from_service_account_json(Credentials_File)

table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

from validacion_dataframes import validar_y_comparar
validar_y_comparar(Hoja_satisfaccion.title, DF, client_bq, table_ref)

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