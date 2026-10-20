"""
Lectura y normalización de la lista de cédulas desde un archivo Excel/CSV.
"""

import os
import re

import pandas as pd

# Nombres de columna que aceptamos como "la columna de cédulas" (sin
# distinguir mayúsculas/minúsculas ni tildes/espacios).
NOMBRES_COLUMNA_CEDULA = {
    "cedula",
    "cédula",
    "documento",
    "numerodocumento",
    "numero_documento",
    "nrodocumento",
    "cc",
}


def _normalizar_encabezado(nombre: str) -> str:
    nombre = str(nombre).strip().lower()
    nombre = (
        nombre.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )
    nombre = re.sub(r"[^a-z0-9]", "", nombre)
    return nombre


def _limpiar_cedula(valor) -> str | None:
    """
    Normaliza un valor de cédula a solo dígitos.
    Maneja el caso típico de pandas leyendo la columna como float
    (123456789 -> 123456789.0 -> "123456789").
    """
    if valor is None:
        return None
    texto = str(valor).strip()
    if texto == "" or texto.lower() == "nan":
        return None
    # Quita separadores de miles/puntuación y un posible ".0" final de float
    texto = texto.replace(".0", "") if texto.endswith(".0") else texto
    solo_digitos = re.sub(r"[^0-9]", "", texto)
    return solo_digitos or None


def _cedulas_desde_filas(encabezados: list, filas: list) -> list[str]:
    columna_idx = 0
    for i, encabezado in enumerate(encabezados):
        if _normalizar_encabezado(encabezado) in NOMBRES_COLUMNA_CEDULA:
            columna_idx = i
            break

    cedulas: list[str] = []
    vistas = set()
    for fila in filas:
        valor = fila[columna_idx] if columna_idx < len(fila) else None
        cedula = _limpiar_cedula(valor)
        if cedula and cedula not in vistas:
            cedulas.append(cedula)
            vistas.add(cedula)
    return cedulas


def leer_cedulas(ruta_archivo: str) -> list[str]:
    """
    Lee un archivo .xlsx/.xls/.csv y devuelve la lista de cédulas (strings de
    solo dígitos, sin duplicados, en el orden en que aparecen).
    """
    if not os.path.exists(ruta_archivo):
        raise FileNotFoundError(f"No se encontró el archivo de entrada: {ruta_archivo}")

    extension = os.path.splitext(ruta_archivo)[1].lower()
    if extension in (".xlsx", ".xls"):
        df = pd.read_excel(ruta_archivo, dtype=str)
    elif extension == ".csv":
        df = pd.read_csv(ruta_archivo, dtype=str)
    else:
        raise ValueError(
            f"Formato de archivo no soportado: {extension}. Usa .xlsx, .xls o .csv"
        )

    if df.empty:
        return []

    return _cedulas_desde_filas(df.columns.tolist(), df.astype(object).where(df.notnull(), None).values.tolist())


def extraer_id_spreadsheet(url_o_id: str) -> str:
    """Acepta tanto una URL completa de Google Sheets como un ID ya limpio."""
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url_o_id)
    if match:
        return match.group(1)
    return url_o_id.strip()


def leer_cedulas_desde_sheet(url_o_id: str, servicio_sheets, rango: str = "A:Z") -> list[str]:
    """
    Lee la lista de cédulas desde un Google Sheet. Por defecto lee la primera
    pestaña, columnas A a Z; si necesitas otra pestaña, pasa algo como
    "Hoja2!A:Z" en `rango`.
    """
    spreadsheet_id = extraer_id_spreadsheet("1QPNo9aa4ZZ3Wy3LWK2lSxggMt-j90iWZZHqUJUANJHI")
    respuesta = (
        servicio_sheets.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=rango)
        .execute()
    )
    valores = respuesta.get("values", [])
    if not valores:
        return []

    encabezados = valores[0]
    filas = valores[1:]
    return _cedulas_desde_filas(encabezados, filas)