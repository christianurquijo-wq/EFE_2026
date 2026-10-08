from google.cloud import bigquery
from google.oauth2.service_account import Credentials
import os
import dotenv
from dotenv import load_dotenv
import pandas as pd
from datetime import date

Credenciales = 'credenciales.json'
client_bq = bigquery.Client.from_service_account_json(Credenciales)

load_dotenv(override=True)

PROJECT_ID = os.getenv("PROJECT_ID")
DATA_SET = os.getenv("DATA_SET")

Dataset_ID = f"{PROJECT_ID}.{DATA_SET}"

info_dataset = client_bq.list_tables(Dataset_ID)

Lista_tablas = {}
for tabla in info_dataset:
    if str.lower('unificado') in str.lower(tabla.table_id) and not 'formacion' in str.lower(tabla.table_id) and not 'append' in str.lower(tabla.table_id): 
        from_table = f"{PROJECT_ID}.{DATA_SET}.{tabla.table_id}"
        Lista_tablas[from_table] = tabla.table_id

print(Lista_tablas)

Fecha = date.today()
Fecha_mensualizada = Fecha.strftime("%Y-%m")
print(Fecha_mensualizada)

appends_especiales = ["caracterizacion", "satisfaccion"]

for tabla, nombre in Lista_tablas.items():
    if any(especial in str(nombre).lower() for especial in appends_especiales):
        table_especial = client_bq.query(f"Select * FROM `{tabla}`").to_dataframe()
        df_especial = pd.DataFrame(table_especial)
        df_especial['Fecha'] = pd.to_datetime(df_especial['Fecha'], errors='coerce')
        df_especial['fecha_mes'] = df_especial['Fecha'].dt.strftime('%Y-%m')
        df_especial = df_especial[df_especial["fecha_mes"] == Fecha_mensualizada]
        df_especial["Fecha_Append"] = Fecha_mensualizada
        df_especial["Fecha_Append"] = pd.to_datetime(df_especial["Fecha_Append"])
        df_especial['Fecha_Append'] = df_especial["Fecha_Append"].dt.strftime('%Y-%m')
        tabla_destino_especial = f"{PROJECT_ID}.{DATA_SET}.{nombre}_APPEND"
        df_especial = df_especial.drop(columns=["Fecha", "fecha_mes"])

        job = client_bq.load_table_from_dataframe(
           df_especial,
           tabla_destino_especial,
            job_config = bigquery.LoadJobConfig(
               write_disposition="WRITE_APPEND",
                autodetect=True
            )
        )
        job.result()
        print(f"{tabla_destino_especial} Actualizada exitosamente")
         
for tabla, nombre in Lista_tablas.items():
    if all(especial not in str(nombre).lower() for especial in appends_especiales):
        Table = client_bq.query(f"Select * FROM `{tabla}`").to_dataframe()
        df = pd.DataFrame(Table)
        df['Fecha_Append'] = Fecha_mensualizada
        df['Fecha_Append'] = pd.to_datetime(df['Fecha_Append'])
        df['Fecha_Append'] = df['Fecha_Append'].dt.strftime('%Y-%m')
        Tabla_destino = f"{PROJECT_ID}.{DATA_SET}.{nombre}_APPEND"
        job = client_bq.load_table_from_dataframe(
                df,
                Tabla_destino,
                job_config = bigquery.LoadJobConfig(
                    write_disposition="WRITE_APPEND",
                    autodetect=True)
        )

        job.result()
        print(f"{Tabla_destino} Actualizada exitosamente")
    
print("Periodizacion finalizada")
