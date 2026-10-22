"""
512 Avanza · Listado Kuepa -> BigQuery (oct-2026).

Reemplaza el flujo manual de 512/main.py (generar un .sql con un CASE por cada
correo y pegarlo en Looker Studio). Ahora:
  1. Este script sube la hoja "Listado Kuepa" a la tabla LISTADO_512_AVANZA
     (una fila por correo, con cargo, centro, regional, distrito, edad y FARO).
  2. La consulta de Looker Studio (512/consulta_looker_512.sql) hace JOIN con esa
     tabla. Se pega UNA sola vez; después basta con correr este script.

Corre solo en el lote nocturno (está en la raíz del repo) y con el botón del panel.
"""
import os

import gspread
import numpy as np
import pandas as pd
from dotenv import dotenv_values, load_dotenv
from google.cloud import bigquery
from google.oauth2.service_account import Credentials

load_dotenv(override=True)

# ID del Sheet: Sheets_512 en el .env de la raíz; en local, respaldo en 512/.env (db).
SPREADSHEET_ID = os.getenv("Sheets_512") or dotenv_values(os.path.join("512", ".env")).get("db")
if not SPREADSHEET_ID:
    raise SystemExit("Falta Sheets_512 en el .env (ID del Sheet de 512 Avanza).")

PROJECT_ID = os.getenv("PROJECT_ID")
# La consulta de Looker cruza esta tabla con el SIS (potent-poetry-284019). BigQuery solo
# cruza datasets de la MISMA ubicación (US, southamerica-east1…): si EFE_2026 está en otra,
# define en el .env BQ_DATASET_512 (ej. SIS_512) y BQ_UBICACION_512 (la del SIS) y el
# dataset se crea solo en esa ubicación.
DATASET_ID = os.getenv("BQ_DATASET_512") or os.getenv("DATA_SET")
UBICACION = os.getenv("BQ_UBICACION_512", "").strip()
TABLE_ID = "LISTADO_512_AVANZA"
CREDENTIALS_FILE = "credenciales.json"

# Columna del Sheet -> columna en BigQuery. Los nombres en mayúscula son los MISMOS
# alias que generaba main.py, para que los campos de Looker Studio no cambien.
COLUMNAS = {
    "Cargo:": "CARGO",
    "Centro educativo:": "CENTRO_EDUCATIVO",
    "Regional:": "REGIONAL",
    "Distrito:": "DISTRITO",
    "Edad:": "EDAD",
    "FARO / NO FARO / ATAL": "FARO__NO_FARO__ATAL",
}
COL_CORREO = "Correo electrónico:"

scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly",
          "https://www.googleapis.com/auth/drive.readonly"]
creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
datos = gspread.authorize(creds).open_by_key(SPREADSHEET_ID).worksheet("Listado Kuepa").get_all_values()

df = pd.DataFrame(datos[2:], columns=[h.strip() for h in datos[1]])
faltan = [c for c in [COL_CORREO, *COLUMNAS] if c not in df.columns]
if faltan:
    raise SystemExit(f"La hoja 'Listado Kuepa' no tiene las columnas: {faltan}")

df = df[[COL_CORREO, *COLUMNAS]].rename(columns={COL_CORREO: "CORREO_LISTADO", **COLUMNAS})
df = df.apply(lambda s: s.astype(str).str.strip())
df = df.replace(["", "N/A", "n/a", "N/a", "n/A", "nan"], np.nan)
df["CORREO_LISTADO"] = df["CORREO_LISTADO"].str.lower()
df = df.dropna(subset=["CORREO_LISTADO"])

# Igual que el CASE de main.py: por cada correo y columna gana el primer valor no vacío.
df = df.groupby("CORREO_LISTADO", sort=False, as_index=False).first()
df["EDAD"] = pd.to_numeric(df["EDAD"], errors="coerce").round().astype("Int64")

print(f"Correos en el listado: {len(df)}")

esquema = [bigquery.SchemaField("CORREO_LISTADO", "STRING")] + [
    bigquery.SchemaField(c, "INT64" if c == "EDAD" else "STRING") for c in COLUMNAS.values()]
client_bq = bigquery.Client.from_service_account_json(CREDENTIALS_FILE)
if UBICACION:
    ds = bigquery.Dataset(f"{PROJECT_ID}.{DATASET_ID}")
    ds.location = UBICACION
    ds = client_bq.create_dataset(ds, exists_ok=True)
    if ds.location.lower() != UBICACION.lower():
        raise SystemExit(f"El dataset {DATASET_ID} ya existe en {ds.location}, no en {UBICACION}: usa otro nombre.")
table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"
job = client_bq.load_table_from_dataframe(
    df, table_ref,
    job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE", schema=esquema))
job.result()
print(f"Listado cargado en {table_ref}")
