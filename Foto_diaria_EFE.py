"""
Foto diaria de estados EFE -> BigQuery (base de los KPIs por día / semana / mes).

Cada noche, al final del lote nocturno (trigger.py lo corre de último), copia el estado
ACTUAL de cada persona a dos tablas históricas:

    EFE_2026.Seguimiento_DIARIO     <- Unificado_Seguimiento   (estado y resultado académico)
    EFE_2026.Empleabilidad_DIARIO   <- Unificado_Empleabilidad (contratación y postulaciones)

Así, aunque las tablas Unificado_* se sobrescriban todos los días, queda la historia de cómo
estaba cada persona cada día y el dashboard puede graficar y comparar cualquier periodo.

Diseño pensado para BigQuery SANDBOX (sin facturación):
  - Todo se hace con consultas que escriben en una tabla destino (sin DML, que el sandbox no
    permite) y sin bajar datos al PC: la copia ocurre dentro de BigQuery.
  - Las tablas NO son particionadas (en sandbox las particiones se borran a los 60 días).
  - El sandbox borra cada tabla 60 días después de creada. Para que el historial no se pierda,
    cada corrida le corre la fecha de expiración a hoy + 59 días. Si eso falla, el script
    termina en error y el lote manda la alerta por correo.
  - Columnas fijas y en texto (STRING): si una tabla Unificado cambia de tipo o le falta una
    columna, la foto no se rompe (la columna queda vacía y el script lo avisa).
  - Si corre dos veces el mismo día, la foto de ese día se reemplaza (no se duplica).

    python Foto_diaria_EFE.py              (toma la foto de hoy)
    python Foto_diaria_EFE.py --simular    (muestra qué haría, sin escribir nada)
"""
from __future__ import annotations

import datetime as dt
import os
import sys

from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv(override=True)

CREDENCIALES = "credenciales.json"
PROYECTO = os.getenv("PROJECT_ID") or "sustained-edge-465417-m3"
DATASET = f"{PROYECTO}.{os.getenv('DATA_SET') or 'EFE_2026'}"
ZONA = "America/Bogota"
DIAS_VIGENCIA = 59  # el sandbox no deja pasar de 60

# origen -> (destino, columnas que se guardan). Si una columna no existe en el origen, queda NULL.
FOTOS = {
    "Unificado_Seguimiento": ("Seguimiento_DIARIO", [
        "Documento", "Proyecto", "Programa", "Estado_academico", "Resultado_academico",
        "Ciudad", "Sexo", "Fecha_ingreso_formacion", "Fecha_fin_formacion",
    ]),
    "Unificado_Empleabilidad": ("Empleabilidad_DIARIO", [
        "Documento", "Proyecto", "Estado_academico", "Estado_contratacion",
        "Total_remisiones_postulaciones", "Empresa", "Ciudad",
    ]),
}
AGRUPAR = ["Fecha_Foto", "Proyecto"]  # clustering: las consultas por fecha y proyecto leen menos


def esquema(columnas: list[str]) -> list[bigquery.SchemaField]:
    return ([bigquery.SchemaField("Fecha_Foto", "DATE"),
             bigquery.SchemaField("Foto_TS", "TIMESTAMP")]
            + [bigquery.SchemaField(c, "STRING") for c in columnas])


def asegurar_tabla(bq: bigquery.Client, destino: str, columnas: list[str], simular: bool) -> bigquery.Table | None:
    try:
        return bq.get_table(destino)
    except Exception:
        print(f"  · {destino} no existe: se crea (columnas en texto, agrupada por {', '.join(AGRUPAR)})")
        if simular:
            return None
        t = bigquery.Table(destino, schema=esquema(columnas))
        t.clustering_fields = AGRUPAR
        return bq.create_table(t)


def tomar_foto(bq: bigquery.Client, origen: str, destino: str, columnas: list[str], hoy: str, simular: bool) -> None:
    fuente = bq.get_table(f"{DATASET}.{origen}")
    # BigQuery no distingue mayúsculas en nombres de columna: se compara igual.
    reales = {c.name.lower(): c.name for c in fuente.schema}
    existentes = {c for c in columnas if c.lower() in reales}
    faltan = [c for c in columnas if c not in existentes]
    if "Documento" in faltan:
        raise SystemExit(f"{origen} no tiene la columna Documento: no se puede tomar la foto.")
    if faltan:
        print(f"  ⚠ {origen} no tiene {faltan}: quedan vacías en la foto")

    select = ",\n  ".join(
        f"NULLIF(TRIM(CAST(`{reales[c.lower()]}` AS STRING)), '') AS `{c}`" if c in existentes else f"CAST(NULL AS STRING) AS `{c}`"
        for c in columnas)
    sql_foto = (f"SELECT DATE('{hoy}') AS Fecha_Foto, CURRENT_TIMESTAMP() AS Foto_TS,\n  {select}\n"
                f"FROM `{DATASET}.{origen}`\nWHERE Documento IS NOT NULL")

    tabla = asegurar_tabla(bq, f"{DATASET}.{destino}", columnas, simular)
    ya_hay = 0
    if tabla is not None:
        ya_hay = list(bq.query(f"SELECT COUNT(*) n FROM `{DATASET}.{destino}` "
                               f"WHERE Fecha_Foto = DATE('{hoy}')").result())[0].n

    print(f"  · origen {origen}: {fuente.num_rows:,} filas · ya había {ya_hay:,} filas del {hoy} en {destino}")
    if simular:
        print("    (simulación: no se escribe)")
        return

    if ya_hay:
        # Sin DML: se reescribe la tabla sin el día de hoy y luego se agrega la foto nueva.
        cfg = bigquery.QueryJobConfig(destination=f"{DATASET}.{destino}", write_disposition="WRITE_TRUNCATE",
                                      clustering_fields=AGRUPAR)
        bq.query(f"SELECT * FROM `{DATASET}.{destino}` WHERE Fecha_Foto != DATE('{hoy}')", job_config=cfg).result()
        print(f"    se quitó la foto anterior del {hoy}")

    cfg = bigquery.QueryJobConfig(destination=f"{DATASET}.{destino}", write_disposition="WRITE_APPEND")
    bq.query(sql_foto, job_config=cfg).result()
    n = list(bq.query(f"SELECT COUNT(*) n FROM `{DATASET}.{destino}` WHERE Fecha_Foto = DATE('{hoy}')").result())[0].n
    print(f"    ✔ foto del {hoy} guardada: {n:,} filas")


def extender_vigencia(bq: bigquery.Client, nombre: str) -> str:
    """Corre la expiración a hoy + DIAS_VIGENCIA. Devuelve la nueva fecha o lanza error."""
    t = bq.get_table(f"{DATASET}.{nombre}")
    t.expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=DIAS_VIGENCIA)
    t = bq.update_table(t, ["expires"])
    return f"{t.expires:%Y-%m-%d}" if t.expires else "no expira"


def main() -> None:
    simular = "--simular" in sys.argv
    bq = bigquery.Client.from_service_account_json(CREDENCIALES, project=PROYECTO)
    hoy = list(bq.query(f"SELECT CAST(CURRENT_DATE('{ZONA}') AS STRING) d").result())[0].d
    print(f"Foto diaria EFE · {hoy} · {DATASET}{' · SIMULACIÓN' if simular else ''}")

    errores = []
    for origen, (destino, columnas) in FOTOS.items():
        print(f"\n{origen} -> {destino}")
        try:
            tomar_foto(bq, origen, destino, columnas, hoy, simular)
        except SystemExit:
            raise
        except Exception as e:
            errores.append(f"{destino}: {e}")
            print(f"  ✖ {e}")

    if not simular:
        print("\nVigencia (sandbox):")
        for _, (destino, _) in FOTOS.items():
            try:
                print(f"  · {destino}: expira {extender_vigencia(bq, destino)}")
            except Exception as e:
                errores.append(f"vigencia {destino}: {e}")
                print(f"  ✖ {destino}: no se pudo extender la expiración ({e})")

        for _, (destino, _) in FOTOS.items():
            r = list(bq.query(f"SELECT COUNT(DISTINCT Fecha_Foto) dias, MIN(Fecha_Foto) desde, COUNT(*) filas "
                              f"FROM `{DATASET}.{destino}`").result())[0]
            print(f"  · {destino}: {r.dias} día(s) desde {r.desde} · {r.filas:,} filas")

    if errores:
        sys.exit("Foto diaria con errores:\n  " + "\n  ".join(errores))
    print("\n✔ Foto diaria completa")


if __name__ == "__main__":
    main()
