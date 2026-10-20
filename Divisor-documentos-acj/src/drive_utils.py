"""
Wrapper delgado sobre la API de Google Drive para lo que necesita este
proyecto: buscar archivos/carpetas por nombre exacto dentro de una carpeta,
crear carpetas, descargar y subir/actualizar archivos.

Requiere una cuenta de servicio (Service Account) de Google Cloud con la
API de Drive habilitada, y que las carpetas de Drive del proyecto hayan
sido compartidas (como mínimo "Editor", o agregadas como miembro con rol
"Administrador de contenido" si están dentro de una Unidad Compartida) con
el correo de esa cuenta de servicio. Ver README.md.
"""

import io
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from . import config

MIME_TYPE_CARPETA = "application/vnd.google-apps.folder"
MIME_TYPE_PDF = "application/pdf"


def _escapar_para_query(texto: str) -> str:
    return texto.replace("'", "\\'")


def obtener_servicio_drive(ruta_credenciales: str = None):
    ruta_credenciales = ruta_credenciales or config.RUTA_CREDENCIALES
    if not os.path.exists(ruta_credenciales):
        raise FileNotFoundError(
            "No se encontró el archivo de credenciales de la cuenta de servicio en: "
            f"{ruta_credenciales}\n"
            "Revisa el README.md para saber cómo generarlo y dónde colocarlo."
        )
    credenciales = service_account.Credentials.from_service_account_file(
        ruta_credenciales, scopes=config.SCOPES
    )
    return build("drive", "v3", credentials=credenciales, cache_discovery=False)


def obtener_servicio_sheets(ruta_credenciales: str = None):
    ruta_credenciales = ruta_credenciales or config.RUTA_CREDENCIALES
    if not os.path.exists(ruta_credenciales):
        raise FileNotFoundError(
            "No se encontró el archivo de credenciales de la cuenta de servicio en: "
            f"{ruta_credenciales}\n"
            "Revisa el README.md para saber cómo generarlo y dónde colocarlo."
        )
    credenciales = service_account.Credentials.from_service_account_file(
        ruta_credenciales, scopes=config.SCOPES
    )
    return build("sheets", "v4", credentials=credenciales, cache_discovery=False)


def buscar_archivo_por_nombre_exacto(service, carpeta_id: str, nombre: str):
    nombre_escapado = _escapar_para_query(nombre)
    query = (
        f"'{carpeta_id}' in parents and name = '{nombre_escapado}' "
        f"and mimeType != '{MIME_TYPE_CARPETA}' and trashed = false"
    )
    respuesta = (
        service.files()
        .list(
            q=query,
            fields="files(id, name, modifiedTime)",
            orderBy="modifiedTime desc",
            pageSize=10,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    archivos = respuesta.get("files", [])
    return archivos[0] if archivos else None


def buscar_carpeta_por_nombre_exacto(service, carpeta_padre_id: str, nombre: str):
    nombre_escapado = _escapar_para_query(nombre)
    query = (
        f"'{carpeta_padre_id}' in parents and name = '{nombre_escapado}' "
        f"and mimeType = '{MIME_TYPE_CARPETA}' and trashed = false"
    )
    respuesta = (
        service.files()
        .list(
            q=query,
            fields="files(id, name)",
            pageSize=10,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    carpetas = respuesta.get("files", [])
    return carpetas[0] if carpetas else None


def crear_carpeta(service, carpeta_padre_id: str, nombre: str):
    metadata = {
        "name": nombre,
        "mimeType": MIME_TYPE_CARPETA,
        "parents": [carpeta_padre_id],
    }
    return (
        service.files()
        .create(body=metadata, fields="id, name", supportsAllDrives=True)
        .execute()
    )


def obtener_o_crear_carpeta_participante(service, carpeta_padre_id: str, cedula: str):
    carpeta = buscar_carpeta_por_nombre_exacto(service, carpeta_padre_id, cedula)
    if carpeta:
        return carpeta["id"], False
    carpeta = crear_carpeta(service, carpeta_padre_id, cedula)
    return carpeta["id"], True


def descargar_archivo(service, file_id: str, ruta_destino: str):
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    with io.FileIO(ruta_destino, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        listo = False
        while not listo:
            _, listo = downloader.next_chunk()


def subir_o_actualizar_archivo(
    service, carpeta_id: str, nombre_archivo: str, ruta_local: str
):
    media = MediaFileUpload(ruta_local, mimetype=MIME_TYPE_PDF, resumable=True)
    existente = buscar_archivo_por_nombre_exacto(service, carpeta_id, nombre_archivo)
    if existente:
        return (
            service.files()
            .update(
                fileId=existente["id"],
                media_body=media,
                fields="id, name",
                supportsAllDrives=True,
            )
            .execute()
        )
    metadata = {"name": nombre_archivo, "parents": [carpeta_id]}
    return (
        service.files()
        .create(
            body=metadata,
            media_body=media,
            fields="id, name",
            supportsAllDrives=True,
        )
        .execute()
    )