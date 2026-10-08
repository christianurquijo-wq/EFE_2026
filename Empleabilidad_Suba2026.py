import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from google.cloud import bigquery
from pathlib import Path
import dotenv
from dotenv import load_dotenv
import os

load_dotenv(override=True)

SPREADSHEET_ID = os.getenv("Data_suba_empleabilidad")
RANGE = "A2:BE"

PROJECT_ID = os.getenv("PROJECT_ID")
DATASET_ID = os.getenv("DATA_SET")
TABLE_ID   = "SUBA_2026_Empleabilidad"

CREDENTIALS_FILE = "credenciales.json"

scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
client_sheets = gspread.authorize(creds)
sheet = client_sheets.open_by_key(SPREADSHEET_ID).worksheet("Empleabilidad")

data = sheet.get_all_values()
headers = data[1]
headers = [h if h != "" else f"col_{i}" for i, h in enumerate(headers)]
num_cols = len(headers)

rows_fixed = []
for i, row in enumerate(data[2:]):
    if not any(cell.strip() for cell in row if cell):
        continue
    row = (row + [None] * num_cols)[:num_cols]
    rows_fixed.append(row)

df = pd.DataFrame(rows_fixed, columns=headers)
df = df.replace(r'^\s*$', None, regex=True)
df = df.where(pd.notnull(df), None)
df = df.dropna(how="all")
df = df.replace(r'^\s*$', None, regex=True)

df.columns = (
    df.columns
    .astype(str)
    .str.strip()
    .str.replace(" ", "_")
    .str.replace(r"[^\w]", "", regex=True)
    .str.lower()
    .str.normalize('NFKD')
    .str.encode('ascii', errors='ignore')
    .str.decode('utf-8')
    .str.replace(r"[^a-z0-9_#]", "", regex=True) 
)

df = df.loc[:, df.columns.notna()]
df = df.loc[:, df.columns != ""]
df = df.loc[:, ~df.columns.duplicated()]
df = df.dropna(subset=['documento_de_identidad'])

df.columns = [col if col != "" else f"col_{i}" for i, col in enumerate(df.columns)]
df = df.drop(columns=['correo_de_la_empresa_2', 'correo_de_la_empresa_3', 'requistos_2', 'correo_de_la_empresa_1'])

df = df.astype(str)
df["total_remisiones"].apply(pd.to_numeric, errors='coerce')

df['proyecto'] = 'Suba es Oportunidad'
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