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

PROJECT_ID = "sustained-edge-465417-m3"
DATASET_ID = "EFE_2026"
TABLE_ID   = "COLSUBSIDIO_2026_Satisfaccion"

CREDENTIALS_FILE = "credenciales.json"

scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
client_sheets = gspread.authorize(creds)

sheet = client_sheets.open_by_key(SPREADSHEET_ID).worksheet("Satisfacción")
data = sheet.get_all_values()

headers = data[1]
rows = data[2:]
headers = [h if h != "" else f"col_{i}" for i, h in enumerate(headers)]
num_cols = len(headers)

rows_fixed = []

for row in rows:
    if not any(cell.strip() for cell in row if cell):
        continue
    row = (row + [None] * num_cols)[:num_cols]
    rows_fixed.append(row)

df = pd.DataFrame(rows_fixed, columns=headers)
df = df.replace(r'^\s*$', None, regex=True)
df = df.where(pd.notnull(df), None)
df = df[df.notna().any(axis=1)]
df = df.dropna(axis=1, how='all')

df.columns = (
    df.columns
    .astype(str)
    .str.strip()
    .str.replace(" ", "_")
    .str.replace(r"[^\w]", "", regex=True)
    .str.lower()
)

df = df.loc[:, ~df.columns.duplicated()]
if df.empty:
    raise ValueError("❌ DataFrame vacío. Revisa estructura del Sheet.")

df['proyecto'] = 'Colsubsidio 2026' 
print(f"# Filas {len(df)}")
print(df.columns.to_list())


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
