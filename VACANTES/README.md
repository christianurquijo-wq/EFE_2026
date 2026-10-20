# Automated Job Market Intelligence Pipeline (elempleo.com)

[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://docs.python.org/3/)
[![Selenium](https://img.shields.io/badge/Selenium-43B02A?style=for-the-badge&logo=selenium&logoColor=white)](https://www.selenium.dev/documentation/)
[![Pandas](https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white)](https://pandas.pydata.org/docs/)
[![Google Sheets API](https://img.shields.io/badge/Google%20Sheets%20API-4285F4?style=for-the-badge&logo=google-sheets&logoColor=white)](https://developers.google.com/sheets/api)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Project Status: Active](https://img.shields.io/badge/Project%20Status-Active-green.svg?style=for-the-badge)](https://github.com/)

Este repositorio contiene un pipeline automatizado de extracción, transformación, enriquecimiento y carga de datos (ETL) diseñado para recopilar inteligencia de mercado laboral desde el portal de empleo `elempleo.com`. El sistema extrae de forma programática ofertas de trabajo bajo criterios específicos, realiza un raspado profundo de segundo nivel para enriquecer los registros, filtra la información mediante expresiones regulares y sincroniza los resultados en tiempo real con una hoja de cálculo en Google Sheets y un archivo CSV local.

---

## Índice

1. [Valor de Negocio y Objetivos Analíticos](#1-valor-de-negocio-y-objetivos-analíticos)
2. [Arquitectura del Sistema y Flujo de Datos](#2-arquitectura-del-sistema-y-flujo-de-datos)
3. [Requisitos del Sistema y Dependencias](#3-requisitos-del-sistema-y-dependencias)
4. [Configuración e Instalación](#4-configuración-e-instalación)
5. [Análisis Detallado del Código](#5-análisis-detallado-del-coódigo)
6. [Estructura de Datos de Salida (Payload)](#6-estructura-de-datos-de-salida-payload)
7. [Estrategia de Optimización y Robustez](#7-estrategia-de-optimización-y-robustez)

---

## 1. Valor de Negocio y Objetivos Analíticos

Este desarrollo resuelve la necesidad de monitorear de forma sistemática el mercado laboral para perfiles técnicos y operativos en Bogotá, eliminando la recolección manual de datos y proporcionando una base de datos estructurada para la toma de decisiones estratégicas.

### Impacto y Capacidades de Diagnóstico

*   **Medición de la Oferta Salarial Real**: Al filtrar ofertas con "Salario confidencial", el pipeline permite calcular promedios, medianas y desviaciones estándar de los salarios reales ofrecidos en el mercado para los sectores de "Mercadeo y Ventas" y "Auxiliar Administrativo".
*   **Diagnóstico de Requisitos Educativos**: Permite diagnosticar si las empresas están sobreexigiendo requisitos académicos para roles operativos, correlacionando el nivel educativo exigido ("técnico", "media", "bachiller") con la compensación económica ofrecida.
*   **Resolución de Asimetría de Información**: Proporciona a las áreas de recursos humanos o analistas de políticas públicas un panorama claro y actualizado de la competitividad de sus vacantes frente al mercado activo.
*   **Acotación de Perfiles No Viables**: Excluye automáticamente contratos de aprendizaje y salarios no declarados, asegurando que el análisis se concentre únicamente en ofertas de empleo formal y directo.
*   **Optimización del Sourcing**: Automatiza la detección de nuevas ofertas ordenadas por fecha de publicación, permitiendo a los reclutadores o buscadores de empleo reaccionar en menos de 24 horas ante nuevas publicaciones.
*   **Estandarización de Datos No Estructurados**: Transforma descripciones de texto libre y metadatos embebidos en el DOM (como variables de Google Analytics 4) en un esquema de datos relacional y limpio.
*   **Repensar la Captura de Datos**: En lugar de depender de APIs costosas o limitadas, el script aprovecha los payloads de telemetría interna (`data-ga4-offerdata`) que la misma plataforma utiliza, garantizando la obtención de datos estructurados con un mínimo de llamadas al DOM.

---

## 2. Arquitectura del Sistema y Flujo de Datos

El pipeline sigue una arquitectura lineal de cinco etapas (Extracción, Filtrado Inicial, Enriquecimiento, Filtrado Avanzado y Carga):

```
+-----------------------------------------------------------------------+
|                           1. EXTRACCIÓN                               |
| - Inicializa Selenium (Headless Chrome)                               |
| - Aplica filtros de salario vía URL                                   |
| - Extrae tarjetas de vacantes y parsea JSON de GA4 del DOM            |
+----------------------------------+------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|                        2. FILTRADO INICIAL                            |
| - Remueve "Contrato de aprendizaje"                                   |
| - Remueve "Salario confidencial"                                      |
| - Elimina registros duplicados                                        |
+----------------------------------+------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|                        3. ENRIQUECIMIENTO                             |
| - Navega de forma iterativa a la URL de cada vacante                  |
| - Extrae: Descripción detallada, Nivel Educativo y Fecha Publicación  |
| - Parsea fechas relativas/locales usando 'dateparser'                 |
+----------------------------------+------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|                        4. FILTRADO AVANZADO                           |
| - Filtra por nivel educativo usando Regex (técnico, media, bachiller) |
| - Ordena cronológicamente de forma descendente                        |
+----------------------------------+------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|                            5. CARGA (LPT)                             |
| - Exporta dataset enriquecido a CSV local                             |
| - Autentica con Google Drive & Sheets API vía Service Account         |
| - Limpia y actualiza la hoja de cálculo "VACANTES"                    |
+-----------------------------------------------------------------------+
```

---

## 3. Requisitos del Sistema y Dependencias

Para ejecutar este pipeline, el entorno de ejecución debe contar con dependencias tanto a nivel de sistema operativo como a nivel de lenguaje de programación.

### Requisitos a Nivel de Sistema Operativo

1.  **Google Chrome Browser**: Debe estar instalado en el sistema operativo. En entornos Linux (servidores/CI-CD), se requiere la instalación de Chrome y sus dependencias de renderizado de fuentes.
2.  **Google Chrome Driver**: Requerido para que Selenium interactúe con el navegador. Debe corresponder exactamente con la versión de Google Chrome instalada. *Nota: Las versiones recientes de Selenium gestionan esto automáticamente mediante Selenium Manager, pero se recomienda asegurar la disponibilidad del binario en el PATH en entornos restringidos.*
3.  **Certificados CA**: Necesarios para establecer conexiones seguras HTTPS con Google APIs y el portal de empleo.

### Dependencias de Python

Las librerías requeridas están especificadas en el archivo `requirements.txt`:

```text
selenium
pandas
python-dotenv
gspread
oauth2client
dateparser
```

---

## 4. Configuración e Instalación

### Paso 1: Clonar el repositorio y preparar el entorno virtual

```bash
git clone https://github.com/tu-usuario/job-market-intelligence-pipeline.git
cd job-market-intelligence-pipeline
python3 -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Paso 2: Configurar las Credenciales de Google Cloud Platform (GCP)

1.  Vaya a la consola de Google Cloud.
2.  Habilite la **Google Drive API** y la **Google Sheets API**.
3.  Cree una **Cuenta de Servicio (Service Account)** y descargue la clave privada en formato JSON.
4.  Guarde este archivo en la raíz del proyecto con el nombre `gcp-credentials.json` (asegúrese de que esté incluido en su `.gitignore`).
5.  Comparta su hoja de cálculo de Google Sheets con el correo electrónico de la cuenta de servicio generada (ej. `mi-servicio@applied-plexus.iam.gserviceaccount.com`) otorgándole permisos de **Editor**.

### Paso 3: Configurar las Variables de Entorno

Cree un archivo `.env` en la raíz del proyecto con la siguiente estructura:

```env
Sheets_JAE=ID_DE_TU_HOJA_DE_CALCULO_GOOGLE_SHEETS
```

*Nota: El ID de la hoja de cálculo se encuentra en la URL de la misma: `https://docs.google.com/spreadsheets/d/ID_DE_TU_HOJA_DE_CALCULO/edit`*

---

## 5. Análisis Detallado del Código

### 1. Extracción de Vacantes y Consumo de Telemetría Interna

La función `extraccion_vacantes` utiliza Selenium en modo headless para evitar la sobrecarga de renderizado de interfaz gráfica. En lugar de parsear cada elemento visual de la tarjeta de empleo, el script accede al atributo `data-ga4-offerdata`. Este atributo contiene un objeto JSON estructurado con los metadatos de la oferta, lo que garantiza una extracción limpia y previene fallos por cambios menores en el diseño HTML (CSS).

```python
# Fragmento clave de extracción de metadatos estructurados
json_data = vacante.get_attribute("data-ga4-offerdata")
if json_data:
    datos_por_oferta = json.loads(json_data)
    datos_totales.append({
        "Vacante": datos_por_oferta.get("title", ""),
        "Empresa": datos_por_oferta.get("company", "Empresa Confidencial"),
        "Ubicación": datos_por_oferta.get("location", ""),
        "Cargo_Equivalente": datos_por_oferta.get("equivalentPositions", ""),
        "Tipo_Contrato": tipo_contrato,
        "Salario": datos_por_oferta.get("salary", "Sin información salarial"),
        "Link_Oferta": link_info_vacante,                    
    })
```

### 2. Enriquecimiento de Datos y Normalización de Fechas

Una vez consolidada la lista de URLs de vacantes válidas, el pipeline realiza una navegación profunda a cada enlace para extraer la descripción completa, el nivel educativo y la fecha de publicación. 

El uso de `dateparser` es crítico aquí, ya que las fechas de publicación en portales de empleo suelen expresarse en lenguaje natural relativo (ej. "Publicado hace 2 días", "Publicado ayer"). `dateparser` normaliza estas cadenas a objetos de tipo `datetime` estándar, permitiendo su posterior ordenamiento cronológico.

```python
# Extracción de fecha y parseo de lenguaje natural a formato ISO
Fecha_publicacion_vacante = Wait_10_Sec.until(
    EC.presence_of_element_located(
        (By.XPATH, '//p[contains(@class, "publish-date-info")]')
    )
)
# Remueve ruido de texto y parsea la fecha
Fecha_publicacion = dateparser.parse(
    Fecha_publicacion_vacante.text.replace("Publicado", "")
).strftime('%Y-%m-%d')
```

### 3. Filtrado Avanzado por Expresiones Regulares

Para acotar el universo de datos a perfiles técnicos y operativos, se aplica un filtro basado en expresiones regulares sobre la columna `Nivel`. Esto descarta perfiles profesionales, especializados o tecnólogos si no cumplen con el criterio de búsqueda.

```python
# Filtrado por niveles educativos específicos (Técnico, Educación Media, Bachillerato)
CSV = CSV[CSV['Nivel'].str.contains(r't[eé]cnic[oa]|media|bachi', case=False, na=False)]
```

### 4. Sincronización con Google Sheets API

La integración con Google Sheets se realiza mediante `gspread`. Se limpia la hoja de destino por completo para evitar colisiones de datos antiguos y se realiza una actualización masiva en una sola llamada de red (`update`), optimizando la cuota de peticiones de la API de Google.

```python
# Preparación de matriz de datos (incluyendo cabeceras) para actualización masiva
CSV_TO_SHEETS = [Datos_Vacantes_Seleccionadas.columns.values.tolist()] + Datos_Vacantes_Seleccionadas.values.tolist()

# Limpieza y escritura atómica
Hoja_de_Trabajo.clear()
Hoja_de_Trabajo.update(range_name="A1", values=CSV_TO_SHEETS)
```

---

## 6. Estructura de Datos de Salida (Payload)

El pipeline genera un archivo estructurado (tanto en formato CSV como en la hoja de cálculo de Google) que cumple con el siguiente esquema de datos:

### Ejemplo de Salida (JSON Representation)

```json
[
  {
    "Vacante": "Auxiliar de Operaciones y Mercadeo",
    "Empresa": "Empresa de Logística y Distribución S.A.S.",
    "Ubicación": "Bogotá",
    "Cargo_Equivalente": "Auxiliar de mercadeo, Auxiliar administrativo",
    "Tipo_Contrato": "Término Indefinido",
    "Salario": "1500000",
    "Link_Oferta": "https://www.elempleo.com/co/ofertas-empleo/auxiliar-de-operaciones-y-mercadeo/1882746190",
    "Programa_Asociado": "Mercadeo y Ventas",
    "Descripción": "Se requiere bachiller o técnico con experiencia mínima de 1 año en procesos de apoyo logístico, inventarios, atención al cliente y soporte administrativo en puntos de venta...",
    "Nivel": "Técnico",
    "Fecha Publicación": "2023-10-27"
  },
  {
    "Vacante": "Auxiliar de Archivo y Correspondencia",
    "Empresa": "Servicios Temporales Empresa 1",
    "Ubicación": "Bogotá",
    "Cargo_Equivalente": "Auxiliar de oficina, Auxiliar de archivo",
    "Tipo_Contrato": "Obra o Labor",
    "Salario": "1300000",
    "Link_Oferta": "https://www.elempleo.com/co/ofertas-empleo/auxiliar-de-archivo-y-correspondencia/1882745540",
    "Programa_Asociado": "Auxiliar Administrativo",
    "Descripción": "Importante compañía requiere bachiller con experiencia en gestión documental, radicación de correspondencia y atención de conmutador...",
    "Nivel": "Educación Media / Bachillerato",
    "Fecha Publicación": "2023-10-26"
  }
]
```

---

## 7. Estrategia de Optimización y Robustez

*   **Headless Execution**: El uso de `--headless` reduce drásticamente el consumo de memoria RAM y CPU en el servidor de ejecución, permitiendo correr este script en instancias de cómputo pequeñas (como AWS EC2 t2.micro o Google Cloud Compute Engine f1-micro).
*   **Explicit Waits**: En lugar de utilizar pausas estáticas (`time.sleep`), el script implementa `WebDriverWait` combinado con `expected_conditions`. Esto asegura que el script continúe la ejecución tan pronto como el elemento DOM esté disponible, optimizando el tiempo total de ejecución del pipeline.
*   **Manejo de Excepciones Granular**: Cada bloque crítico (extracción de contrato, parseo de JSON, navegación profunda) está envuelto en estructuras `try-except`. Si una vacante específica presenta una estructura corrupta o un error de carga, el pipeline la ignora y continúa con el procesamiento de las demás, garantizando la resiliencia del proceso global.
*   **Filtrado de Ruido en Origen**: Al aplicar filtros de salario directamente en los parámetros de la URL (`Flitro_salarios`), se reduce el volumen de datos innecesarios transferidos por la red, optimizando el ancho de banda y el procesamiento local de Pandas.