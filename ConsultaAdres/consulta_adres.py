import os
import random
import unicodedata
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SHEET_URL = "https://docs.google.com/spreadsheets/d/1LxOaVnC_Ev6UqzAl9I89zSR1oo7lK0b8O_McyA5kxus/edit?gid=0#gid=0"
CREDENCIALES = "credenciales.json"
CARPETA_SCREENSHOTS_LOCAL = "screenshots"
CARPETA_DRIVE_ID = "1p4VvI8TALQcpWraj6lF3xkcB6SidLXzy"
URL_CONSULTA = "https://aplicaciones.adres.gov.co/BDUA_Internet/Pages/ConsultarAfiliadoWeb_2.aspx"

os.makedirs(CARPETA_SCREENSHOTS_LOCAL, exist_ok=True)

COL_ESTADO = 3
COL_FECHA = 4
COL_ARCHIVO = 5
COL_TEXTO = 6

MAPA_TIPO_DOC = {
    "CC": "CC", "CEDULA DE CIUDADANIA": "CC",
    "TI": "TI", "TARJETA DE IDENTIDAD": "TI",
    "CE": "CE", "CEDULA DE EXTRANJERIA": "CE",
    "PA": "PA", "PASAPORTE": "PA",
    "RC": "RC", "REGISTRO CIVIL": "RC",
    "NU": "NU", "NO. UNICO DE ID. PERSONAL": "NU",
    "AS": "AS", "ADULTO SIN IDENTIFICACION": "AS",
    "MS": "MS", "MENOR SIN IDENTIFICACION": "MS",
    "CD": "CD", "CARNET DIPLOMATICO": "CD",
    "CN": "CN", "CERTIFICADO NACIDO VIVO": "CN",
    "SC": "SC", "SALVO CONDUCTO": "SC",
    "PE": "PE", "PER ESPECIAL PERMANENCIA": "PE",
    "PT": "PT", "PERMISO POR PROTECCION TEMPORAL": "PT",
    "PC": "PC", "PEP-TUTOR": "PC",
}

def normalizar_tipo_doc(texto):
    texto = texto.strip().upper()
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    return MAPA_TIPO_DOC.get(texto)

scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]
creds = Credentials.from_service_account_file(CREDENCIALES, scopes=scopes)
gc = gspread.authorize(creds)
sheet = gc.open_by_url(SHEET_URL).sheet1
drive_service = build("drive", "v3", credentials=creds)

def subir_a_drive(ruta_local, nombre_archivo):
    query = f"name='{nombre_archivo}' and '{CARPETA_DRIVE_ID}' in parents and trashed=false"
    resultado = drive_service.files().list(
        q=query, fields="files(id)",
        supportsAllDrives=True, includeItemsFromAllDrives=True
    ).execute()
    existentes = resultado.get("files", [])

    media = MediaFileUpload(ruta_local, mimetype="image/png")

    if existentes:
        archivo_id = existentes[0]["id"]
        archivo = drive_service.files().update(
            fileId=archivo_id, media_body=media, fields="id, webViewLink",
            supportsAllDrives=True
        ).execute()
    else:
        metadata = {"name": nombre_archivo, "parents": [CARPETA_DRIVE_ID]}
        archivo = drive_service.files().create(
            body=metadata, media_body=media, fields="id, webViewLink",
            supportsAllDrives=True
        ).execute()

    return archivo.get("webViewLink")

filas = sheet.get_all_values()[1:]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    for idx, fila in enumerate(filas, start=2):
        tipo_doc_raw = fila[0].strip() if len(fila) > 0 else ""
        cedula = fila[1].strip() if len(fila) > 1 else ""
        estado_actual = fila[2] if len(fila) > 2 else ""

        if not cedula:
            continue
        if estado_actual:
            continue

        tipo_doc = normalizar_tipo_doc(tipo_doc_raw)
        if not tipo_doc:
            sheet.update_cell(idx, COL_ESTADO, f"Tipo de documento no reconocido: {tipo_doc_raw}")
            continue

        print(f"Consultando {tipo_doc} {cedula}...")

        try:
            page.goto(URL_CONSULTA)
            page.select_option("#tipoDoc", tipo_doc)
            page.fill("#txtNumDoc", cedula)
            try:
                page.wait_for_function(
                    "typeof grecaptcha !== 'undefined' && typeof grecaptcha.execute === 'function'",
                    timeout=8000
                )
            except PlaywrightTimeoutError:
                pass

            page.wait_for_timeout(500)

            pagina_resultado = page
            es_popup = False
            try:
                with page.context.expect_page(timeout=6000) as popup_info:
                    page.click("#btnConsultar")
                pagina_resultado = popup_info.value
                pagina_resultado.wait_for_load_state()
                es_popup = True
            except PlaywrightTimeoutError:
                page.wait_for_timeout(2000)
            print(f"  -> popup detectado: {es_popup}")

            if pagina_resultado == page:
                texto_error = page.locator("#Error").inner_text().strip()
                if texto_error:
                    sheet.update_cell(idx, COL_ESTADO, f"No encontrado / Error: {texto_error[:80]}")
                    sheet.update_cell(idx, COL_FECHA, str(datetime.now()))
                    page.wait_for_timeout(random.randint(5000, 12000))
                    continue

            nombre_archivo = f"{tipo_doc}_{cedula}.png"
            ruta_local = f"{CARPETA_SCREENSHOTS_LOCAL}/{nombre_archivo}"
            pagina_resultado.screenshot(path=ruta_local, full_page=True)

            tablas = pagina_resultado.locator("table").all_inner_texts()
            texto_resultado = "\n\n".join(tablas).strip()

            if pagina_resultado != page:
                pagina_resultado.close()

            link_drive = subir_a_drive(ruta_local, nombre_archivo)

            sheet.update_cell(idx, COL_ESTADO, "OK")
            sheet.update_cell(idx, COL_FECHA, str(datetime.now()))
            sheet.update_cell(idx, COL_ARCHIVO, link_drive)
            sheet.update_cell(idx, COL_TEXTO, texto_resultado[:5000])  # límite de celda de Sheets

            if pagina_resultado != page:
                pagina_resultado.close()

            link_drive = subir_a_drive(ruta_local, nombre_archivo)

            sheet.update_cell(idx, COL_ESTADO, "OK")
            sheet.update_cell(idx, COL_FECHA, str(datetime.now()))
            sheet.update_cell(idx, COL_ARCHIVO, link_drive)

        except Exception as e:
            print(f"ERROR completo en cédula {cedula}: {e}")
            sheet.update_cell(idx, COL_ESTADO, f"Error: {str(e)[:80]}")
            sheet.update_cell(idx, COL_FECHA, str(datetime.now()))

        page.wait_for_timeout(random.randint(5000, 12000))

    browser.close()

print("Consulta finalizada.")