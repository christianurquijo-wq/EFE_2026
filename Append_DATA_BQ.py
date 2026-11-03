"""
APPEND mensual EFE -> BigQuery: agrega el corte de un mes a las tablas <Unificado_X>_APPEND.

  - Seguimiento, Empleabilidad y demás Unificado_*: copia completa de la tabla tal como está hoy
    (el «corte» del mes).
  - Caracterización y Satisfacción: solo los registros cuya Fecha cae en ese mes.
  - Cada fila lleva Fecha_Append = 'AAAA-MM'.

    python Append_DATA_BQ.py --simular            (muestra qué haría, sin escribir)
    python Append_DATA_BQ.py                       (mes por defecto, ver abajo)
    python Append_DATA_BQ.py --mes 2026-10         (un mes concreto)
    python Append_DATA_BQ.py --mes 2026-10 --reemplazar   (si ese mes ya estaba cargado, lo rehace)

Mes por defecto (nov-2026): del día 1 al 10 se carga el mes ANTERIOR (cierre de mes); del 25 en
adelante, el mes en curso. Entre el 11 y el 24 pide --mes para no cargar un mes a medias.
Antes el mes salía siempre de la fecha de hoy: correrlo el 3 de noviembre etiquetaba los datos
como noviembre y filtraba Satisfacción/Caracterización a 3 días.

No duplica: si la tabla APPEND ya tiene filas de ese mes, la salta (o la rehace con --reemplazar).
Sandbox: sin DML; el reemplazo reescribe la tabla sin ese mes con una consulta.
"""
import argparse
import sys
from datetime import date

import pandas as pd
from dotenv import load_dotenv
from google.cloud import bigquery
from google.cloud.exceptions import NotFound
from google.oauth2.service_account import Credentials
import os

load_dotenv(override=True)

CREDENCIALES = "credenciales.json"
# drive.readonly: algunas Unificado_* son vistas sobre tablas enlazadas a Google Sheets.
SCOPES = ["https://www.googleapis.com/auth/bigquery", "https://www.googleapis.com/auth/drive.readonly"]
PROJECT_ID = os.getenv("PROJECT_ID")
DATA_SET = os.getenv("DATA_SET")
Dataset_ID = f"{PROJECT_ID}.{DATA_SET}"
appends_especiales = ["caracterizacion", "satisfaccion"]


def mes_por_defecto(hoy: date) -> str:
    if hoy.day <= 10:
        anterior = date(hoy.year - (hoy.month == 1), (hoy.month - 2) % 12 + 1, 1)
        return anterior.strftime("%Y-%m")
    if hoy.day >= 25:
        return hoy.strftime("%Y-%m")
    sys.exit(f"Hoy es {hoy:%d-%m}: a mitad de mes no hay corte claro. Indica el mes: --mes AAAA-MM")


def filas_del_mes(client_bq, destino: str, mes: str) -> int | None:
    """Filas que ya tiene `destino` con ese Fecha_Append (None si la tabla no existe)."""
    try:
        client_bq.get_table(destino)
    except NotFound:
        return None
    sql = f"SELECT COUNT(*) n FROM `{destino}` WHERE CAST(Fecha_Append AS STRING) LIKE '{mes}%'"
    return list(client_bq.query(sql).result())[0].n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", help="AAAA-MM a cargar")
    ap.add_argument("--simular", action="store_true")
    ap.add_argument("--reemplazar", action="store_true", help="rehace el mes si ya estaba cargado")
    args = ap.parse_args()
    mes = args.mes or mes_por_defecto(date.today())
    pd.Period(mes, freq="M")  # valida el formato (error claro si viene mal)

    creds = Credentials.from_service_account_file(CREDENCIALES, scopes=SCOPES)
    client_bq = bigquery.Client(credentials=creds, project=PROJECT_ID)

    Lista_tablas = {}
    for tabla in client_bq.list_tables(Dataset_ID):
        nombre = tabla.table_id.lower()
        if "unificado" in nombre and "formacion" not in nombre and "append" not in nombre:
            Lista_tablas[f"{Dataset_ID}.{tabla.table_id}"] = tabla.table_id

    print(f"APPEND mensual · mes {mes} · {len(Lista_tablas)} tablas"
          + (" · SIMULACIÓN" if args.simular else "") + (" · REEMPLAZAR" if args.reemplazar else ""))
    errores, resumen = [], []
    for tabla, nombre in Lista_tablas.items():
        destino = f"{Dataset_ID}.{nombre}_APPEND"
        especial = any(e in nombre.lower() for e in appends_especiales)
        try:
            df = client_bq.query(f"SELECT * FROM `{tabla}`").to_dataframe()
            if especial:
                fechas = pd.to_datetime(df["Fecha"], errors="coerce")
                sin_fecha = int(fechas.isna().sum())
                df = df[fechas.dt.strftime("%Y-%m") == mes].drop(columns=["Fecha"])
                nota = f" (registros con Fecha en {mes}; {sin_fecha} sin fecha válida no entran)"
            else:
                nota = " (corte completo)"
            df["Fecha_Append"] = mes

            ya = filas_del_mes(client_bq, destino, mes)
            estado = "tabla nueva" if ya is None else f"ya tenía {ya:,} filas de {mes}"
            print(f"\n{nombre} -> {nombre}_APPEND: {len(df):,} filas{nota} · {estado}")
            if ya and not args.reemplazar:
                print("   ↷ se salta (ya estaba cargado). Usa --reemplazar para rehacerlo.")
                resumen.append((nombre, "saltada", ya))
                continue
            if df.empty:
                print("   ⚠ 0 filas para ese mes: no se escribe nada.")
                resumen.append((nombre, "sin datos", 0))
                continue
            if args.simular:
                resumen.append((nombre, "simulada", len(df)))
                continue
            if ya:
                cfg = bigquery.QueryJobConfig(destination=destino, write_disposition="WRITE_TRUNCATE")
                client_bq.query(f"SELECT * FROM `{destino}` WHERE NOT (CAST(Fecha_Append AS STRING) LIKE '{mes}%')",
                                job_config=cfg).result()
                print(f"   se quitaron las {ya:,} filas anteriores de {mes}")
            job = client_bq.load_table_from_dataframe(
                df, destino, job_config=bigquery.LoadJobConfig(write_disposition="WRITE_APPEND", autodetect=True))
            job.result()
            n = filas_del_mes(client_bq, destino, mes)
            print(f"   ✔ {destino} actualizada: {n:,} filas de {mes}")
            resumen.append((nombre, "cargada", n))
        except Exception as e:  # noqa: BLE001 -- una tabla con problemas no detiene las demás
            errores.append(f"{nombre}: {e}")
            print(f"   ✖ {e}")

    print("\nResumen:")
    for nombre, estado, n in resumen:
        print(f"   {nombre:<35} {estado:<10} {n:>8,}")
    if errores:
        sys.exit("APPEND con errores:\n  " + "\n  ".join(errores))
    print("Periodizacion finalizada")


if __name__ == "__main__":
    main()
