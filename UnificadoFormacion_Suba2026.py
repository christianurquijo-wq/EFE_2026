import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from google.cloud import bigquery
from pathlib import Path
import dotenv
from dotenv import load_dotenv
import os

load_dotenv(override=True)
SPREADSHEET_ID = os.getenv("Data_looker_suba")
SHEET_NAME = "UnificadoFormacion"

PROJECT_ID = os.getenv("PROJECT_ID")
DATASET_ID = os.getenv("DATA_SET")
TABLE_ID   = "SUBA_2026_UnificadoFormacion"

CREDENTIALS_FILE = "credenciales.json"

scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
client_sheets = gspread.authorize(creds)

sheet = client_sheets.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
data = sheet.get_all_values()

if len(data) < 2:
    raise ValueError("❌ El sheet no tiene datos suficientes")

headers = data[0]
headers = [h if h != "" else f"col_{i}" for i, h in enumerate(headers)]
num_cols = len(headers)

rows_fixed = []

for row in data[1:]:
    if not any(cell.strip() for cell in row if cell):
        continue

    row = (row + [None] * num_cols)[:num_cols]
    rows_fixed.append(row)

df = pd.DataFrame(rows_fixed, columns=headers)

print(f"📥 Filas leídas: {len(df)}")
print(f"📥 Columnas leídas: {len(df.columns)}")

df = df.replace(r'^\s*$', None, regex=True)
df.columns = (
    df.columns
    .astype(str)
    .str.strip()
    .str.lower()
    .str.replace(" ", "_")
    .str.replace(r"[^\w]", "", regex=True)
    .str.normalize('NFKD')
    .str.encode('ascii', errors='ignore')
    .str.decode('utf-8')
    .str.replace(r"[^a-z0-9_#]","", regex=True)

)

df = df.loc[:, ~df.columns.duplicated()]
for col in df.columns:
    if "asistencia" in col or "%" in col:
        print(f"📊 Procesando porcentaje: {col}")

        df[col] = (
            df[col]
            .astype(str)
            .str.replace("%", "", regex=False)
            .str.replace(",", ".", regex=False)
            .str.strip()
        )

        df[col] = pd.to_numeric(df[col], errors="coerce") / 100

for col in df.columns:
    if any(x in col for x in ["id", "documento", "telefono", "valor"]):
        try:
            df[col] = pd.to_numeric(df[col], errors="ignore")
        except:
            pass
if df.empty:
    raise ValueError("❌ DataFrame vacío")

df['fecha_finalizacion'] = pd.to_datetime(df['fecha_finalizacion'])
df['fecha_finalizacion'] = df['fecha_finalizacion'].dt.strftime('%d/%m/%Y')

df['fecha_inicio'] = pd.to_datetime(df['fecha_inicio'])
df['fecha_inicio'] = df['fecha_inicio'].dt.strftime('%d/%m/%Y')
df['proyecto'] = 'Suba es Oportunidad'

print(df.columns.to_list())

client_bq = bigquery.Client.from_service_account_json(CREDENTIALS_FILE)
table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

from validacion_dataframes import validar_y_comparar

print("Iniciando control de calidad de columnas")
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