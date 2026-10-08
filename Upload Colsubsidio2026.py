import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from google.cloud import bigquery
from pathlib import Path
import dotenv
from dotenv import load_dotenv
import os

load_dotenv(override=True)

SPREADSHEET_ID = os.getenv("Sheets_Colsubsidio")
RANGE = "A5:BP"

PROJECT_ID = os.getenv("PROJECT_ID")
DATASET_ID = os.getenv("DATA_SET")
TABLE_ID   = "COLSUBSIDIO_2026_V2"

CREDENTIALS_FILE = "credenciales.json"

scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
client_sheets = gspread.authorize(creds)

sheet = client_sheets.open_by_key(SPREADSHEET_ID).sheet1
data = sheet.get(RANGE)

headers = data[0]
rows = data[1:]

df = pd.DataFrame(rows, columns=headers)

df = df.dropna(how="all")
df = df.replace(r'^\s*$', None, regex=True)

cols_before = set(df.columns)
df = df.dropna(axis=1, how='all')
cols_after = set(df.columns)

eliminadas = cols_before - cols_after

df.columns = (
    df.columns
    .astype(str)
    .str.strip()
    .str.replace(" ", "_")
    .str.replace(r"[^\w]", "", regex=True)
    .str.lower()
)


df = df.loc[:, df.columns.notna()]
df = df.loc[:, df.columns != ""]
df = df.loc[:, ~df.columns.duplicated()]
df.columns = [col if col != "" else f"col_{i}" for i, col in enumerate(df.columns)]


df = df.astype(str)

df['proyecto'] = 'Colsubsidio 2026'
df = df.drop(columns=['coincide_fecha_inicio'])
print(df.columns.tolist())

client_bq = bigquery.Client.from_service_account_json(CREDENTIALS_FILE)
table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

from validacion_dataframes import validar_y_comparar
validar_y_comparar(sheet.title, df, client_bq, table_ref)

job = client_bq.load_table_from_dataframe(
    df,
    table_ref,
    job_config=bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
        autodetect=True
    )
)

job.result()

print("Verificado")