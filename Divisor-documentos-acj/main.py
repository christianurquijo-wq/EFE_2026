import argparse
import csv
import datetime
import logging
import os
import sys
import tempfile

from src import config, drive_utils
from src.cedulas import leer_cedulas, leer_cedulas_desde_sheet
from src.pdf_utils import PDFInvalidoError, dividir_pdf

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("divisor_acj")


def parsear_argumentos():
    parser = argparse.ArgumentParser(description="Divide documentos ACJ + CC por cédula desde Google Drive.")
    parser.add_argument(
        "--input", "-i", default=None,
        help="Ruta al archivo .xlsx/.xls/.csv con la lista de cédulas a procesar. "
             "Si no se indica, se usa --sheet-url.",
    )
    parser.add_argument(
        "--sheet-url", default="1QPNo9aa4ZZ3Wy3LWK2lSxggMt-j90iWZZHqUJUANJHI",
        help="URL (o ID) del Google Sheet con la lista de cédulas (por defecto: tu hoja configurada).",
    )
    parser.add_argument(
        "--sheet-range", default="A:A",
        help="Pestaña/rango a leer del Sheet, ej: 'Hoja2!A:Z' (por defecto: A:Z de la primera pestaña).",
    )
    parser.add_argument(
        "--source-folder-id", default=config.CARPETA_ORIGEN_ID,
        help="ID de la carpeta de Drive donde están los documentos a dividir.",
    )
    parser.add_argument(
        "--dest-parent-id", default=config.CARPETA_PARTICIPANTES_ID,
        help="ID de la carpeta de Drive donde viven/se crean las carpetas por cédula.",
    )
    parser.add_argument(
        "--credentials", default=config.RUTA_CREDENCIALES,
        help="Ruta al JSON de la cuenta de servicio de Google.",
    )
    parser.add_argument(
        "--output-report", default=None,
        help="Ruta del CSV de reporte de resultados (por defecto: reporte_<fecha_hora>.csv).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="No descarga/sube/crea nada en Drive; solo indica qué haría con cada cédula.",
    )
    return parser.parse_args()


def procesar_cedula(service, cedula: str, args, carpeta_temporal: str) -> dict:
    """Procesa una cédula y devuelve una fila de reporte (dict)."""
    fila = {"cedula": cedula, "estado": "", "detalle": ""}

    nombre_origen = f"{cedula}{config.SUFIJO_ARCHIVO_ORIGEN}"
    archivo_origen = drive_utils.buscar_archivo_por_nombre_exacto(
        service, args.source_folder_id, nombre_origen
    )
    if not archivo_origen:
        fila["estado"] = "NO_ENCONTRADO"
        fila["detalle"] = f"No se encontró '{nombre_origen}' en la carpeta de origen."
        log.warning("Cédula %s: %s", cedula, fila["detalle"])
        return fila

    if args.dry_run:
        fila["estado"] = "OK (dry-run)"
        fila["detalle"] = f"Se encontró '{nombre_origen}'; se dividiría y subiría a la carpeta '{cedula}'."
        log.info("Cédula %s: %s", cedula, fila["detalle"])
        return fila

    ruta_local_origen = os.path.join(carpeta_temporal, f"{cedula}_origen.pdf")
    ruta_local_acj = os.path.join(carpeta_temporal, f"{cedula}{config.SUFIJO_ACJ}")
    ruta_local_cc = os.path.join(carpeta_temporal, f"{cedula}{config.SUFIJO_CC}")

    try:
        drive_utils.descargar_archivo(service, archivo_origen["id"], ruta_local_origen)
        resultado = dividir_pdf(ruta_local_origen, ruta_local_acj, ruta_local_cc)

        carpeta_id, fue_creada = drive_utils.obtener_o_crear_carpeta_participante(
            service, args.dest_parent_id, cedula
        )

        drive_utils.subir_o_actualizar_archivo(
            service, carpeta_id, f"{cedula}{config.SUFIJO_ACJ}", ruta_local_acj
        )
        drive_utils.subir_o_actualizar_archivo(
            service, carpeta_id, f"{cedula}{config.SUFIJO_CC}", ruta_local_cc
        )

        fila["estado"] = "OK"
        detalle = f"Carpeta {'creada' if fue_creada else 'existente'}. {resultado.total_paginas} páginas procesadas."
        if resultado.advertencia:
            fila["estado"] = "OK_CON_ADVERTENCIA"
            detalle += f" ADVERTENCIA: {resultado.advertencia}"
        fila["detalle"] = detalle
        log.info("Cédula %s: %s", cedula, detalle)

    except PDFInvalidoError as e:
        fila["estado"] = "ERROR_PDF"
        fila["detalle"] = str(e)
        log.error("Cédula %s: %s", cedula, e)
    except Exception as e:  # noqa: BLE001 - queremos registrar cualquier falla y seguir con la siguiente cédula
        fila["estado"] = "ERROR"
        fila["detalle"] = f"{type(e).__name__}: {e}"
        log.error("Cédula %s: error inesperado: %s", cedula, e)
    finally:
        for ruta in (ruta_local_origen, ruta_local_acj, ruta_local_cc):
            if os.path.exists(ruta):
                os.remove(ruta)

    return fila


def escribir_reporte(filas: list[dict], ruta_reporte: str):
    with open(ruta_reporte, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["cedula", "estado", "detalle"])
        writer.writeheader()
        writer.writerows(filas)


def main():
    args = parsear_argumentos()

    if not args.input:
        try:
            servicio_sheets = drive_utils.obtener_servicio_sheets(args.credentials)
        except FileNotFoundError as e:
            log.error(str(e))
            sys.exit(1)
        cedulas = leer_cedulas_desde_sheet(args.sheet_url, servicio_sheets, args.sheet_range)
        origen = args.sheet_url
    else:
        cedulas = leer_cedulas(args.input)
        origen = args.input

    if not cedulas:
        log.error("No se encontraron cédulas en: %s", origen)
        sys.exit(1)
    log.info("Se leyeron %d cédula(s) de %s", len(cedulas), origen)

    service = None
    try:
        service = drive_utils.obtener_servicio_drive(args.credentials)
    except FileNotFoundError as e:
        if args.dry_run:
            log.warning("%s\nContinuando dry-run sin verificar Drive (no se validará si los archivos existen).", e)
        else:
            log.error(str(e))
            sys.exit(1)

    filas_reporte = []
    with tempfile.TemporaryDirectory(prefix="divisor_acj_") as carpeta_temporal:
        for cedula in cedulas:
            if service is not None:
                fila = procesar_cedula(service, cedula, args, carpeta_temporal)
            else:
                fila = {"cedula": cedula, "estado": "SIN_VERIFICAR", "detalle": "No hay credenciales configuradas."}
            filas_reporte.append(fila)

    ruta_reporte = args.output_report or f"reporte_{datetime.datetime.now():%Y%m%d_%H%M%S}.csv"
    escribir_reporte(filas_reporte, ruta_reporte)

    conteo = {}
    for fila in filas_reporte:
        conteo[fila["estado"]] = conteo.get(fila["estado"], 0) + 1
    log.info("Resumen: %s", conteo)
    log.info("Reporte detallado guardado en: %s", ruta_reporte)


if __name__ == "__main__":
    main()
