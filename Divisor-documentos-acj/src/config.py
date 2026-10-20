
import os

# ID de la carpeta donde llegan los documentos a dividir
# (https://drive.google.com/drive/folders/1iGa9RI1IKv79Yk-O-PDC2WCi4pdTRVuM)
CARPETA_ORIGEN_ID = os.environ.get(
    "CARPETA_ORIGEN_ID", "1iGa9RI1IKv79Yk-O-PDC2WCi4pdTRVuM"
)

# ID de la carpeta donde viven (o se crean) las subcarpetas por cédula
# (https://drive.google.com/drive/folders/19Hs8lBMtjs3oiCIiFeB3SoWiMkFcrSsw)
CARPETA_PARTICIPANTES_ID = os.environ.get(
    "CARPETA_PARTICIPANTES_ID", "1flIGi79kSRHMKD6PtrEEcX3ShsUscqv9"
)

# Ruta al JSON de credenciales de la cuenta de servicio de Google Cloud.
RUTA_CREDENCIALES = os.environ.get(
    "GOOGLE_APPLICATION_CREDENTIALS",
    os.path.join(os.path.dirname(__file__), "..", "credentials", "service_account.json"),
)

# Sufijo fijo que tienen los documentos a dividir: "<cedula>_001AcuerdoCompromiso.pdf"
SUFIJO_ARCHIVO_ORIGEN = "_001AcuerdoCompromiso.pdf"

# Sufijos de los archivos resultantes: "<cedula>_ACJ.pdf" y "<cedula>_CC.pdf"
SUFIJO_ACJ = "_ACJ.pdf"
SUFIJO_CC = "_CC.pdf"

# Páginas del documento original que corresponden a cada parte (basado en 1, inclusive)
PAGINAS_ACJ = (1, 4)  # páginas 1 a 4
PAGINA_CC = 5  # página 5

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]
