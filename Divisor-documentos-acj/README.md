# Divisor de documentos ACJ / Cédula

Script en Python para dividir automáticamente los PDFs de cada participante
(páginas 1-4 = Acuerdo de Compromiso / ACJ, página 5 = documento de
identidad / CC) y organizarlos en Google Drive, en una carpeta por cédula.

## Qué hace, en palabras simples

1. Lees una lista de cédulas desde un Excel o CSV.
2. Por cada cédula, el script busca en la carpeta de "documentos a dividir"
   de Drive un archivo llamado `<cedula>_001AcuerdoCompromiso.pdf`.
3. Si lo encuentra, lo separa en dos PDFs: `<cedula>_ACJ.pdf` (páginas 1 a 4)
   y `<cedula>_CC.pdf` (página 5).
4. Busca si ya existe una carpeta con el nombre de esa cédula dentro de la
   carpeta de "participantes". Si existe, guarda ahí los dos archivos; si no
   existe, la crea primero.
5. El archivo original **no se mueve ni se borra**: queda igual en la
   carpeta de origen.
6. Al final genera un reporte en CSV (`reporte_AAAAMMDD_HHMMSS.csv`) que
   dice, cédula por cédula, si todo salió bien, si no se encontró el
   documento, o si hubo algún error — para que puedas revisar rápido qué
   quedó pendiente sin tener que abrir Drive.

Si vuelves a correr el script con una cédula que ya fue procesada antes, no
duplica archivos: sobreescribe el ACJ y el CC existentes en la carpeta de
esa cédula.

## Configuración inicial (una sola vez)

### 1. Crear la cuenta de servicio en Google Cloud

1. Entra a [Google Cloud Console](https://console.cloud.google.com/) y crea
   un proyecto (o usa uno existente de Datágil).
2. Habilita la **Google Drive API** para ese proyecto (menú "APIs y
   servicios" → "Habilitar APIs y servicios" → busca "Google Drive API").
3. Ve a "APIs y servicios" → "Credenciales" → "Crear credenciales" →
   "Cuenta de servicio". Dale un nombre, por ejemplo
   `divisor-documentos-acj`.
4. Ya creada, entra a la cuenta de servicio → pestaña "Claves" → "Agregar
   clave" → "Crear clave nueva" → tipo **JSON**. Se descargará un archivo.
5. Renombra ese archivo a `service_account.json` y colócalo en la carpeta
   `credentials/` de este proyecto (nunca lo subas a git ni lo compartas).
6. Copia el correo de la cuenta de servicio (algo como
   `divisor-documentos-acj@tu-proyecto.iam.gserviceaccount.com`, lo
   encuentras en la misma pantalla).

### 2. Compartir las carpetas de Drive con la cuenta de servicio

Comparte **ambas** carpetas con ese correo, dándole permiso de **Editor**:

- Carpeta de documentos a dividir:
  https://drive.google.com/drive/folders/1oXOk8wYzNQmpr5uSxNC_Kz-eXXrOOU42
- Carpeta de carpetas de participantes:
  https://drive.google.com/drive/folders/1J9SbekCDE63gWDyaNtNOyxP_DfpXFzk7

(Clic derecho sobre la carpeta en Drive → "Compartir" → pega el correo de
la cuenta de servicio → rol "Editor" → "Enviar".)

Los IDs de estas dos carpetas ya están puestos por defecto en
`src/config.py`; si algún día cambian de carpeta, actualiza los IDs ahí (o
pásalos por línea de comandos, ver más abajo).

### 3. Instalar dependencias

```bash
python3 -m venv venv
source venv/bin/activate        # en Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Uso

1. Prepara un Excel o CSV con una columna de cédulas (ver
   `ejemplo_lista_cedulas.csv`). El script detecta automáticamente una
   columna llamada "cedula", "cédula", "documento" o similar; si no
   encuentra ninguna, usa la primera columna del archivo.

2. Corre el script:

```bash
python main.py --input ejemplo_lista_cedulas.csv
```

3. Revisa el reporte CSV que se genera en la misma carpeta
   (`reporte_AAAAMMDD_HHMMSS.csv`) para ver qué cédulas quedaron `OK`,
   cuáles `NO_ENCONTRADO` (no había documento en la carpeta de origen con
   ese nombre) y cuáles tuvieron algún error.

### Modo de prueba (dry-run)

Para verificar qué haría el script SIN subir, crear ni modificar nada en
Drive (solo confirma si el archivo de cada cédula existe en la carpeta de
origen):

```bash
python main.py --input ejemplo_lista_cedulas.csv --dry-run
```

### Otras opciones

```bash
python main.py --input lista.xlsx \
  --source-folder-id <otro_id_de_carpeta_origen> \
  --dest-parent-id <otro_id_de_carpeta_participantes> \
  --credentials ruta/a/otras_credenciales.json \
  --output-report reporte_lote_septiembre.csv
```

## Estados posibles en el reporte

| Estado | Significado |
|---|---|
| `OK` | Se encontró, dividió y subió correctamente. |
| `OK_CON_ADVERTENCIA` | Se procesó, pero el PDF original no tenía exactamente 5 páginas (revisar manualmente). |
| `NO_ENCONTRADO` | No existe en la carpeta de origen un archivo `<cedula>_001AcuerdoCompromiso.pdf`. |
| `ERROR_PDF` | El archivo encontrado no se pudo leer como PDF válido (ej: menos de 2 páginas). |
| `ERROR` | Falla inesperada (de red, de permisos de Drive, etc.); el detalle trae el mensaje exacto. |

## Supuestos y límites de esta primera versión

- El nombre del archivo origen debe ser **exactamente**
  `<cedula>_001AcuerdoCompromiso.pdf` (coincidencia exacta, no búsqueda
  parcial). Si el patrón real varía, hay que ajustarlo en
  `src/config.py` (`SUFIJO_ARCHIVO_ORIGEN`).
- Si hay más de un archivo con el mismo nombre en la carpeta de origen
  (Drive lo permite), se usa el modificado más recientemente.
- Costo de infraestructura: **cero** — solo usa tu cuenta de Google Drive
  existente (dentro de las cuotas gratuitas de la API de Drive, que son
  muy holgadas para este volumen) y corre en tu equipo o en cualquier
  máquina donde instales Python.

## Pruebas automáticas

La lógica de división de PDF y de lectura de cédulas tiene pruebas que no
requieren Drive ni credenciales:

```bash
pip install pytest
python -m pytest tests/ -v
```
