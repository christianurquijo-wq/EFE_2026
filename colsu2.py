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


#Fecha = date.today()
Fecha = date(2026, 6, 1)
print(Fecha)
Fecha_mensualizada = Fecha.strftime("%Y-%m")
print(Fecha_mensualizada)



for tabla, nombre in Lista_tablas.items():
    Table = client_bq.query(f"Select * FROM `{tabla}`").to_dataframe()
    df = pd.DataFrame(Table)
    Proyectos = df['Proyecto'].unique()
    if not df.empty:
        if 'Colsubsidio 2.0 2026' in Proyectos:
            df = df[df['Proyecto'] == 'Colsubsidio 2.0 2026']
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
