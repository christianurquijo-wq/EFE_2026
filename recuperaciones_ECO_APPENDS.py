import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from google.cloud import bigquery
import dotenv 
from dotenv import load_dotenv
import os
from datetime import date
import numpy as np

load_dotenv(override=True) 

PROJECT_ID = os.getenv("PROJECT_ID")
DATASET_ID = "EFE_2026"
TABLE_ID_ORIGEN = "ECOPLUS_V2_2026"
TABLE_ID_DESTINO   = "RECUPERACIONES_ECOPLUS_2026"

Credentials_File = "credenciales.json"
client_bq = bigquery.Client.from_service_account_json(Credentials_File)

tabla_seguimiento = table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_ORIGEN}"
datos = client_bq.query(f"SELECT * FROM {tabla_seguimiento}").to_dataframe()
df = pd.DataFrame(datos)

df = df[df["novedad"] == "Activo"]

columnas_interes = ["documento", "id_sis", "gestor_asignado","novedad",
                    "programa", "ciudad", "modulo_que_cursa", "cantidad_de_modulos_cursados", 
                    "cantidad_de_modulos_aprobados"]

df = df[columnas_interes]

df['estado_aprobacion'] = np.where(
    df["cantidad_de_modulos_cursados"] == 0, "Pendiente por Ingresar",
    np.where(
        df["cantidad_de_modulos_aprobados"] != df["cantidad_de_modulos_cursados"], 
        "Con Pendientes Académicos", "Al día"))

df['proyecto'] = "Ecolombia 2.0"

fecha_registro = date.today().strftime("%Y-%m-%d")
df["fecha_monitoreo"] = fecha_registro

print(df.columns.to_list())
print(df)

client_bq = bigquery.Client.from_service_account_json(Credentials_File)
table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_DESTINO}"

query_fecha = client_bq.query(f"SELECT DISTINCT fecha_monitoreo FROM {table_ref} ORDER BY fecha_monitoreo DESC").to_dataframe()
ultima_fecha = query_fecha["fecha_monitoreo"].iloc[0]

validacion = ultima_fecha == fecha_registro

if validacion:
    df_historico = client_bq.query(f"SELECT * FROM {table_ref}").to_dataframe()
    df_historico = df_historico[df_historico["fecha_monitoreo"].astype(str) != str(fecha_registro)]
    df_final = pd.concat([df_historico, df], ignore_index=True)
    job = client_bq.load_table_from_dataframe(
    df_final,
    table_ref,
    job_config=bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
        autodetect=True
        )
    )
    job.result()
    print("Actualización hoy Completada con Éxtio")

else:
    job = client_bq.load_table_from_dataframe(
    df,
    table_ref,
    job_config=bigquery.LoadJobConfig(
        write_disposition="WRITE_APPEND",
        autodetect=True
        )
    )

    job.result()
    print("Agregación monitoreo diario completo")