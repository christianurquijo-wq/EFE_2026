# Automated Job Market Intelligence Pipeline (elempleo.com)

[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://docs.python.org/3/)
[![Selenium](https://img.shields.io/badge/Selenium-43B02A?style=for-the-badge&logo=selenium&logoColor=white)](https://www.selenium.dev/documentation/)
[![Pandas](https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white)](https://pandas.pydata.org/docs/)
[![Google Sheets API](https://img.shields.io/badge/Google%20Sheets%20API-4285F4?style=for-the-badge&logo=google-sheets&logoColor=white)](https://developers.google.com/sheets/api)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Project Status: Active](https://img.shields.io/badge/Project%20Status-Active-green.svg?style=for-the-badge)](https://github.com/)

This repository contains an automated Extract, Transform, and Load (ETL) pipeline designed to gather job market intelligence from the job portal `elempleo.com`. The system programmatically extracts job postings based on specific criteria, performs deep second-level web scraping to enrich records, filters information using regular expressions (Regex), and synchronizes results in real-time with a Google Sheets spreadsheet and a local CSV file.

---

## Table of Contents

1. [Business Value and Analytical Objectives](#1-business-value-and-analytical-objectives)
2. [System Architecture and Data Flow](#2-system-architecture-and-data-flow)
3. [System Requirements and Dependencies](#3-system-requirements-and-dependencies)
4. [Configuration and Installation](#4-configuration-and-installation)
5. [Detailed Code Analysis](#5-detailed-code-analysis)
6. [Output Data Structure (Payload)](#6-output-data-structure-payload)
7. [Optimization and Robustness Strategy](#7-optimization-and-robustness-strategy)

---

## 1. Business Value and Analytical Objectives

This project addresses the need to systematically monitor the job market for technical and operational roles in Bogotá, eliminating manual data collection and providing a structured database for strategic decision-making.

### Impact and Diagnostic Capabilities

*   **Real Salary Offering Measurement**: By filtering out postings with "Confidential Salary" ("Salario confidencial"), the pipeline enables the calculation of averages, medians, and standard deviations of actual salaries offered in the market for the "Marketing and Sales" ("Mercadeo y Ventas") and "Administrative Assistant" ("Auxiliar Administrativo") sectors.
*   **Educational Requirements Diagnosis**: It allows diagnosing whether companies are over-demanding academic requirements for operational roles by correlating the required educational level (`Nivel`) (such as "technical", "middle school", "high school") with the financial compensation offered.
*   **Information Asymmetry Resolution**: It provides human resources departments or public policy analysts with a clear, up-to-date overview of the competitiveness of their vacancies against the active market.
*   **Exclusion of Non-Viable Profiles**: It automatically excludes apprenticeship contracts and undeclared salaries, ensuring that the analysis focuses solely on formal and direct employment offers.
*   **Sourcing Optimization**: It automates the detection of new job offers sorted by publication date, allowing recruiters or job seekers to react within 24 hours of new postings.
*   **Unstructured Data Standardization**: It transforms free-text descriptions and embedded DOM metadata (such as Google Analytics 4 variables) into a clean, relational data schema.
*   **Rethinking Data Capture**: Instead of relying on expensive or rate-limited APIs, the script leverages internal telemetry payloads (`data-ga4-offerdata`) used by the platform itself, ensuring structured data retrieval with minimal DOM queries.

---

## 2. System Architecture and Data Flow

The pipeline follows a linear five-stage architecture (Extraction, Initial Filtering, Enrichment, Advanced Filtering, and Loading):

```
+-----------------------------------------------------------------------+
|                           1. EXTRACTION                               |
| - Initializes Selenium (Headless Chrome)                              |
| - Applies salary filters via URL                                      |
| - Extracts job cards and parses GA4 JSON from the DOM                 |
+----------------------------------+------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|                        2. INITIAL FILTERING                           |
| - Removes "Contrato de aprendizaje" (Apprenticeship contracts)        |
| - Removes "Salario confidencial" (Confidential salaries)              |
| - Eliminates duplicate records                                        |
+----------------------------------+------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|                           3. ENRICHMENT                               |
| - Iteratively navigates to each job vacancy URL                       |
| - Extracts: Detailed Description, Educational Level, and Pub Date     |
| - Parses relative/local dates using 'dateparser'                      |
+----------------------------------+------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|                        4. ADVANCED FILTERING                          |
| - Filters by educational level using Regex (technical, middle, high)  |
| - Sorts chronologically in descending order                           |
+----------------------------------+------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|                            5. LOADING (LPT)                           |
| - Exports enriched dataset to local CSV                               |
| - Authenticates with Google Drive & Sheets API via Service Account    |
| - Clears and updates the "VACANTES" spreadsheet                       |
+----------------------------------+------------------------------------+
```

---

## 3. System Requirements and Dependencies

To run this pipeline, the execution environment must meet dependencies at both the operating system and programming language levels.

### Operating System Requirements

1.  **Google Chrome Browser**: Must be installed on the operating system. In Linux environments (servers/CI-CD), Chrome and its font-rendering dependencies are required.
2.  **Google Chrome Driver**: Required for Selenium to interact with the browser. It must match the installed Google Chrome version exactly. *Note: Recent Selenium versions manage this automatically via Selenium Manager, but ensuring binary availability in the PATH is recommended for restricted environments.*
3.  **CA Certificates**: Necessary to establish secure HTTPS connections with Google APIs and the job portal.

### Python Dependencies

The required libraries are specified in the `requirements.txt` file:

```text
selenium
pandas
python-dotenv
gspread
oauth2client
dateparser
```

---

## 4. Configuration and Installation

### Step 1: Clone the repository and prepare the virtual environment

```bash
git clone https://github.com/your-username/job-market-intelligence-pipeline.git
cd job-market-intelligence-pipeline
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Step 2: Configure Google Cloud Platform (GCP) Credentials

1.  Go to the Google Cloud Console.
2.  Enable the **Google Drive API** and the **Google Sheets API**.
3.  Create a **Service Account** and download the private key in JSON format.
4.  Save this file in the project root directory as `gcp-credentials.json` (ensure it is added to your `.gitignore`).
5.  Share your Google Sheets spreadsheet with the generated service account email (e.g., `my-service@applied-plexus.iam.gserviceaccount.com`) granting it **Editor** permissions.

### Step 3: Configure Environment Variables

Create a `.env` file in the project root with the following structure:

```env
Sheets_JAE=YOUR_GOOGLE_SHEETS_SPREADSHEET_ID
```

*Note: The spreadsheet ID can be found in its URL: `https://docs.google.com/spreadsheets/d/YOUR_SPREADSHEET_ID/edit`*

---

## 5. Detailed Code Analysis

### 1. Vacancy Extraction and Internal Telemetry Consumption

The `extraccion_vacantes` function uses Selenium in headless mode to avoid GUI rendering overhead. Instead of parsing each visual element of the job card, the script accesses the `data-ga4-offerdata` attribute. This attribute contains a structured JSON object with the vacancy's metadata, ensuring clean extraction and preventing failures due to minor HTML (CSS) layout changes.

```python
# Key snippet for structured metadata extraction
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

### 2. Data Enrichment and Date Normalization

Once the list of valid vacancy URLs is consolidated, the pipeline performs deep navigation to each link to extract the full description, educational level, and publication date. 

The use of `dateparser` is critical here, as publication dates on job portals are often expressed in relative natural language (e.g., "Publicado hace 2 días", "Publicado ayer"). `dateparser` normalizes these strings into standard `datetime` objects, enabling subsequent chronological sorting.

```python
# Date extraction and natural language parsing to ISO format
Fecha_publicacion_vacante = Wait_10_Sec.until(
    EC.presence_of_element_located(
        (By.XPATH, '//p[contains(@class, "publish-date-info")]')
    )
)
# Removes text noise and parses the date
Fecha_publicacion = dateparser.parse(
    Fecha_publicacion_vacante.text.replace("Publicado", "")
).strftime('%Y-%m-%d')
```

### 3. Advanced Filtering via Regular Expressions

To narrow down the data scope to technical and operational profiles, a regular expression-based filter is applied to the `Nivel` (Level) column. This discards professional, specialized, or technologist profiles if they do not meet the search criteria.

```python
# Filtering by specific educational levels (Technical, Middle School, High School)
CSV = CSV[CSV['Nivel'].str.contains(r't[eé]cnic[oa]|media|bachi', case=False, na=False)]
```

### 4. Synchronization with Google Sheets API

Integration with Google Sheets is performed using `gspread`. The target sheet is completely cleared to prevent collisions with legacy data, and a bulk update is executed in a single network call (`update`), optimizing the Google API request quota.

```python
# Preparing data matrix (including headers) for bulk update
CSV_TO_SHEETS = [Datos_Vacantes_Seleccionadas.columns.values.tolist()] + Datos_Vacantes_Seleccionadas.values.tolist()

# Atomic clearing and writing
Hoja_de_Trabajo.clear()
Hoja_de_Trabajo.update(range_name="A1", values=CSV_TO_SHEETS)
```

---

## 6. Output Data Structure (Payload)

The pipeline generates a structured file (both in CSV format and in the Google Sheets spreadsheet) that complies with the following data schema:

### Output Example (JSON Representation)

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

## 7. Optimization and Robustness Strategy

*   **Headless Execution**: Using `--headless` drastically reduces RAM and CPU consumption on the execution server, allowing this script to run on small compute instances (such as AWS EC2 t2.micro or Google Cloud Compute Engine f1-micro).
*   **Explicit Waits**: Instead of using static pauses (`time.sleep`), the script implements `WebDriverWait` combined with `expected_conditions`. This ensures that the script resumes execution as soon as the DOM element becomes available, optimizing the overall pipeline execution time.
*   **Granular Exception Handling**: Each critical block (contract extraction, JSON parsing, deep navigation) is wrapped in `try-except` blocks. If a specific vacancy has a corrupted structure or a loading error, the pipeline skips it and continues processing the remaining ones, ensuring the resilience of the overall process.
*   **Noise Filtering at Source**: By applying salary filters directly within the URL parameters (`Flitro_salarios`), the volume of unnecessary data transferred over the network is reduced, optimizing bandwidth and local Pandas processing.