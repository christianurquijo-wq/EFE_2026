"""
Vigencia de tablas y vistas en BigQuery SANDBOX (proyecto sin facturación).

En sandbox, BigQuery BORRA cada tabla y cada VISTA 60 días después de creada. Así se pierden,
por ejemplo, las vistas Unificado_* de EFE_2026, que son la base del lote, de los dashboards
y de la foto diaria. Hasta ahora solo se protegían las tablas *_APPEND (con el respaldo en Drive
de Mantenimiento_appends.py). Las vistas no tenían respaldo.

Este script recorre TODOS los datasets del proyecto y, a todo lo que vence en menos de
UMBRAL_DIAS, le corre la expiración a hoy + 59 días (el máximo del sandbox es 60).
Si BigQuery no deja extender una vista, la vuelve a crear con la misma consulta, lo que
también le da 60 días nuevos. Corre al inicio del lote nocturno (trigger.py).

    python Vigencia_sandbox.py              (extiende lo que vence pronto)
    python Vigencia_sandbox.py --simular    (solo muestra qué vence y cuándo)
    python Vigencia_sandbox.py --todo       (extiende todo, aunque falte mucho)
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
DIAS_VIGENCIA = 59
UMBRAL_DIAS = 45  # se extiende lo que venza antes de esto (evita escribir metadatos todos los días)


def main() -> None:
    simular = "--simular" in sys.argv
    todo = "--todo" in sys.argv
    bq = bigquery.Client.from_service_account_json(CREDENCIALES, project=PROYECTO)
    ahora = dt.datetime.now(dt.timezone.utc)
    nueva = ahora + dt.timedelta(days=DIAS_VIGENCIA)
    limite = ahora + dt.timedelta(days=UMBRAL_DIAS)
    print(f"Vigencia sandbox · {PROYECTO} · nueva expiración {nueva:%Y-%m-%d}{' · SIMULACIÓN' if simular else ''}")

    extendidas, errores, sin_cambio = 0, [], 0
    for ds in bq.list_datasets():
        print(f"\n{ds.dataset_id}")
        for item in bq.list_tables(ds.reference):
            t = bq.get_table(item.reference)
            nombre = f"{ds.dataset_id}.{t.table_id}"
            vence = t.expires
            if vence and vence < ahora + dt.timedelta(days=3):
                marca = "⚠"
            else:
                marca = "·"
            estado = f"vence {vence:%Y-%m-%d}" if vence else "no vence"
            if not vence or (vence > limite and not todo):
                sin_cambio += 1
                continue
            print(f"  {marca} {t.table_type:5} {t.table_id}: {estado}", end="")
            if simular:
                print("  → se extendería")
                continue
            try:
                t.expires = nueva
                t = bq.update_table(t, ["expires"])
                print(f"  → {t.expires:%Y-%m-%d}")
                extendidas += 1
            except Exception as e:
                if t.table_type == "VIEW" and t.view_query:
                    try:
                        # Plan B para vistas: recrearla con la misma consulta (vuelve a tener 60 días).
                        # Respaldo del SQL antes de borrar, por si la creación falla.
                        os.makedirs("vistas_respaldo", exist_ok=True)
                        ruta = os.path.join("vistas_respaldo", f"{ds.dataset_id}.{t.table_id}.sql")
                        with open(ruta, "w", encoding="utf-8") as f:
                            f.write(t.view_query)
                        nueva_vista = bigquery.Table(t.reference)
                        nueva_vista.view_query = t.view_query
                        nueva_vista.description = t.description
                        bq.delete_table(t.reference)
                        creada = bq.create_table(nueva_vista)
                        print(f"  → recreada, vence {creada.expires:%Y-%m-%d}" if creada.expires else "  → recreada")
                        extendidas += 1
                        continue
                    except Exception as e2:
                        e = f"{e2} · el SQL de la vista quedó en {ruta}"
                print(f"  ✖ {e}")
                errores.append(f"{nombre}: {e}")

    print(f"\nResumen: {extendidas} extendidas · {sin_cambio} sin cambio (vencen después de "
          f"{UMBRAL_DIAS} días o no vencen) · {len(errores)} con error")
    if errores:
        sys.exit("No se pudo extender:\n  " + "\n  ".join(errores))


if __name__ == "__main__":
    main()
