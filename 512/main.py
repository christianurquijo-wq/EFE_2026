import os
import gspread
import numpy as np
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from dotenv import load_dotenv

load_dotenv(override=True)

print(os.getenv("db"))

json_sheets = "applied-plexus-476714-n0-d7c1f0400cc6.json"
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
cred_sheets = ServiceAccountCredentials.from_json_keyfile_name(json_sheets, scope)
client = gspread.authorize(cred_sheets)

datos = client.open_by_key(os.getenv('db')).worksheet("Listado Kuepa").get_all_values()
df = pd.DataFrame(datos[2:], columns=datos[1])

df.replace(["N/A", "n/a", "N/a", "n/A"], np.nan, inplace=True)

columnas_condiciones = [
    'Cargo:', 'Centro educativo:', 'Regional:',
    'Distrito:', 'Edad:', 'FARO / NO FARO / ATAL'
]

nombre_archivo = "casos_sql_generados.sql"

# --- BLOQUE SQL ESTATICO: INICIO Y SELECT ---
sql_header = """WITH BASE AS (
  SELECT
    U._ID AS USER,
    U.INCREMENTAL_USER_CODE AS ID_SIS,
    U.PROFILE_EMAIL AS CORREO,
    CONCAT(U.PROFILE_FIRST_NAME," ",U.PROFILE_LAST_NAME) AS NOMBRE_COMPLETO,
    U.PROFILE_DOC_NUMBER AS DOCUMENTO,
    FORMAT_DATE('%d/%m/%Y', DATE(U.PROFILE_BIRTHDAY)) AS FECHA_NACIMIENTO,
    "Republica Dominicana" AS PAIS,
    FORMAT_DATE('%m/%d/%Y', DATE(STAT.CREATED_AT)) AS FECHA_CREACION,
    STRUCTURE.NAME AS CICLO,
    STRUCTURE.NAME AS GRUPO_ACADEMICO,
    AC.NAME AS CURSO,
    S_P.NAME AS acamedic_component_name,
    E100811.NAME AS TIPO_RECURSO,
    COALESCE(ROUND(STAT_DET.COMPLETED_STATUS, 3), 0) AS STATUS_CONSUMO_CONTENIDOS,
    COALESCE(ROUND((STAT_DET.TIME_VIEW/3600), 3), 0) AS HORAS_USO,
    COALESCE(ROUND(STAT_PARENT.COMPLETED_STATUS, 3), 0) AS STATUS_CONSUMO,
    COUNT(DISTINCT STRUCTURE.NAME) OVER (PARTITION BY U._ID) AS TOTAL_GRUPOS,
    COUNT(DISTINCT CASE WHEN STAT_PARENT.COMPLETED_STATUS >= 90 THEN STRUCTURE.NAME ELSE NULL END) OVER (PARTITION BY U._ID) AS GRUPOS_COMPLETOS
  FROM `potent-poetry-284019.DSQD_SIS_us.EQD100010_user` U
  JOIN `potent-poetry-284019.DSQD_SIS_us.EQD100200_user_statistics` STAT
    ON STAT.USER = U._ID
  LEFT JOIN `potent-poetry-284019.DSQD_SIS_us.EQD100100_structure` STRUCTURE
    ON STAT.STRUCTURE = STRUCTURE._ID
  JOIN `potent-poetry-284019.DSQD_SIS_us.EQD100201_statistics` STAT_DET
    ON STAT_DET.__MODEL = STAT._ID
  JOIN `potent-poetry-284019.DSQD_SIS_us.EQD100150_academic_component` AC
    ON STAT_DET.ACADEMIC_COMPONENT = AC._ID
  INNER JOIN `potent-poetry-284019.DSGE_SIS_us.EGE100812_academic_component_category` ACC
    ON AC.ACADEMIC_COMPONENT_CATEGORY = ACC._ID AND ACC._ID = '5fc1416f18d8cca721c0b9e2'
  LEFT JOIN `potent-poetry-284019.DSQD_SIS_us.EQD100150_academic_component` F_P
    ON F_P._ID = AC.PARENT
  LEFT JOIN `potent-poetry-284019.DSQD_SIS_us.EQD100150_academic_component` S_P
    ON F_P.PARENT = S_P._ID AND S_P.ACADEMIC_COMPONENT_CATEGORY = '5fc1416f18d8cca721c0b9e0'
  LEFT JOIN `potent-poetry-284019.DSQD_SIS_us.EQD100201_statistics` STAT_PARENT
    ON STAT_PARENT.__MODEL = STAT._ID AND STAT_PARENT.ACADEMIC_COMPONENT = S_P._ID
  LEFT JOIN `potent-poetry-284019.DSQD_SIS_us.EQD100181_academic_resource_config` E100181
    ON E100181._ID = AC.CONFIG_CONTENT
  LEFT JOIN `potent-poetry-284019.DSQD_SIS_us.EQD100160_academic_resource` E100160
    ON E100160._ID = E100181.ACADEMIC_RESOURCE
  LEFT JOIN `potent-poetry-284019.DSGE_SIS_us.EGE100811_academic_resource_category` E100811
    ON E100811._ID = E100160.ACADEMIC_RESOURCE_CATEGORY
  WHERE STAT.DELETED = 'false' OR STAT.DELETED IS NULL
    AND DATE(STAT.CREATED_AT) >= DATE '2026-10-01'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY AC.NAME, STRUCTURE.NAME, U._ID ORDER BY STAT_DET.COMPLETED_STATUS DESC, AC.NAME DESC) = 1
)
SELECT 
  USER,
  FECHA_CREACION,
  ID_SIS,
  NOMBRE_COMPLETO,
  CORREO,
  DOCUMENTO,
  FECHA_NACIMIENTO,
  PAIS,
  CICLO,
  GRUPO_ACADEMICO,
  CURSO,
  acamedic_component_name,
  STATUS_CONSUMO_CONTENIDOS,
  HORAS_USO,
  STATUS_CONSUMO,
  SUM(HORAS_USO) OVER (PARTITION BY USER) AS TOTAL_HORAS_USO,
  CASE 
    WHEN TOTAL_GRUPOS = GRUPOS_COMPLETOS THEN 'CERTIFICACIONES COMPLETAS OBTENIDAS'
    WHEN GRUPOS_COMPLETOS = 0 THEN 'ACTIVOS SIN CERTIFICACIÓN'
    WHEN GRUPOS_COMPLETOS > 0 AND GRUPOS_COMPLETOS < TOTAL_GRUPOS THEN 'PENDIENTE POR FINALIZAR UNA CERTIFICACIÓN'
    ELSE 'ACTIVOS SIN CERTIFICACIÓN'
  END AS ESTADO_GLOBAL,
"""

# --- BLOQUE SQL ESTATICO: CIERRE ---
sql_footer = """
FROM BASE
ORDER BY USER, GRUPO_ACADEMICO ASC
"""

with open(nombre_archivo, "w", encoding="utf-8") as f:
    f.write(sql_header)
    
    for index, columna in enumerate(columnas_condiciones):
        alias_columna = str(columna).upper().replace(":", "").replace(" ", "_").replace("/", "_").replace("__", "_")

        f.write(f"\n  -- Condicion para {columna}\n")
        f.write("  CASE\n")

        for _, fila in df.iterrows():
            user_email = str(fila.get("Correo electrónico:", "")).strip().lower()
            condicion_loop = str(fila.get(columna, "")).strip()

            if user_email and condicion_loop and condicion_loop.lower() != 'nan':
                condicion_loop_seguro = condicion_loop.replace("'", "''")
                
                # Condición para imprimir como número si es la columna Edad
                if columna == 'Edad:':
                    f.write(f"    WHEN LOWER(TRIM(CORREO)) = '{user_email}' THEN {condicion_loop_seguro}\n")
                else:
                    f.write(f"    WHEN LOWER(TRIM(CORREO)) = '{user_email}' THEN '{condicion_loop_seguro}'\n")

        if index == len(columnas_condiciones) - 1:
            f.write(f"    ELSE NULL\n  END AS {alias_columna}\n")
        else:
            f.write(f"    ELSE NULL\n  END AS {alias_columna},\n")

    f.write(sql_footer)

print(f"Proceso finalizado. Puedes copiar y pegar el contenido de: {nombre_archivo}")