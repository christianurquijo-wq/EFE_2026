import argparse
import csv
import datetime

from src import config, drive_utils

MIME_TYPE_CARPETA = "application/vnd.google-apps.folder"


def parsear_argumentos():
    parser = argparse.ArgumentParser(description="Audita subcarpetas y documentos de la carpeta de participantes.")
    parser.add_argument(
        "--parent-id", default=config.CARPETA_PARTICIPANTES_ID,
        help="ID de la carpeta de Drive a auditar (por defecto: la carpeta de participantes configurada).",
    )
    parser.add_argument(
        "--credentials", default=config.RUTA_CREDENCIALES,
        help="Ruta al JSON de la cuenta de servicio de Google.",
    )
    parser.add_argument(
        "--output", default=None,
        help="Ruta del CSV de salida (por defecto: auditoria_<fecha_hora>.csv).",
    )
    return parser.parse_args()


def listar_todo(service, carpeta_id: str, page_size: int = 1000):
    """Devuelve todos los items (archivos y carpetas) dentro de carpeta_id, paginando si hace falta."""
    items = []
    page_token = None
    while True:
        respuesta = (
            service.files()
            .list(
                q=f"'{carpeta_id}' in parents and trashed = false",
                fields="nextPageToken, files(id, name, mimeType, modifiedTime)",
                pageSize=page_size,
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        items.extend(respuesta.get("files", []))
        page_token = respuesta.get("nextPageToken")
        if not page_token:
            break
    return items


def main():
    args = parsear_argumentos()
    service = drive_utils.obtener_servicio_drive(args.credentials)

    print(f"Listando subcarpetas dentro de: {args.parent_id}")
    items_nivel1 = listar_todo(service, args.parent_id)
    subcarpetas = [item for item in items_nivel1 if item["mimeType"] == MIME_TYPE_CARPETA]

    print(f"Se encontraron {len(subcarpetas)} subcarpetas. Revisando contenido de cada una...")

    # Detectar nombres duplicados (misma cédula con más de una carpeta)
    conteo_por_nombre = {}
    for carpeta in subcarpetas:
        conteo_por_nombre[carpeta["name"]] = conteo_por_nombre.get(carpeta["name"], 0) + 1

    filas = []
    for i, carpeta in enumerate(subcarpetas, start=1):
        nombre_carpeta = carpeta["name"]
        contenido = listar_todo(service, carpeta["id"])
        archivos = [item for item in contenido if item["mimeType"] != MIME_TYPE_CARPETA]
        subcarpetas_internas = [item for item in contenido if item["mimeType"] == MIME_TYPE_CARPETA]

        nombres_archivos = sorted(a["name"] for a in archivos)
        tiene_acj = any(n.endswith(config.SUFIJO_ACJ) for n in nombres_archivos)
        tiene_cc = any(n.endswith(config.SUFIJO_CC) for n in nombres_archivos)

        filas.append({
            "cedula_carpeta": nombre_carpeta,
            "carpeta_id": carpeta["id"],
            "es_duplicada": "SI" if conteo_por_nombre[nombre_carpeta] > 1 else "NO",
            "veces_que_se_repite_el_nombre": conteo_por_nombre[nombre_carpeta],
            "cantidad_archivos": len(archivos),
            "tiene_acj": "SI" if tiene_acj else "NO",
            "tiene_cc": "SI" if tiene_cc else "NO",
            "nombres_archivos": "; ".join(nombres_archivos),
            "subcarpetas_internas_inesperadas": "; ".join(s["name"] for s in subcarpetas_internas),
        })

        if i % 10 == 0 or i == len(subcarpetas):
            print(f"  {i}/{len(subcarpetas)} carpetas revisadas...")

    ruta_salida = args.output or f"auditoria_{datetime.datetime.now():%Y%m%d_%H%M%S}.csv"
    campos = [
        "cedula_carpeta", "carpeta_id", "es_duplicada", "veces_que_se_repite_el_nombre",
        "cantidad_archivos", "tiene_acj", "tiene_cc", "nombres_archivos",
        "subcarpetas_internas_inesperadas",
    ]
    with open(ruta_salida, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(filas)

    duplicadas = sum(1 for f in filas if f["es_duplicada"] == "SI")
    print(f"\nListo. {len(filas)} carpetas auditadas, {duplicadas} con nombre duplicado.")
    print(f"Reporte guardado en: {ruta_salida}")


if __name__ == "__main__":
    main()