import pandas as pd
import dotenv
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from google.cloud import bigquery
import os

Credentials_file = "credenciales.json"

Client_bq = bigquery.Client.from_service_account_json(Credentials_file)
load_dotenv(override=True)

Tabla = os.getenv('BQ_Satisfaccion')

query = f"""SELECT * FROM `{Tabla}`"""

df = Client_bq.query(query).to_dataframe()
df = pd.DataFrame(df)
print(df.columns)


columnas_ignoradas = ['Nombre', 'Documento', 'Empresa']

for columnas in df.columns:

    if columnas in columnas_ignoradas:
        continue
    else:
        valores_unicos = df[columnas].value_counts(dropna=False)

        print(f"{columnas}: [{valores_unicos}]")