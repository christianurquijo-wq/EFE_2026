import selenium
from selenium import webdriver
from selenium.webdriver import chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common import options
import pandas as pd
import os
from dotenv import load_dotenv 
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import dateparser
import sys

URL = "https://www.elempleo.com/co/ofertas-empleo"

def extraccion_vacantes(tematica, numero_paginas: int, ubicacion):
    pagina = 1
    datos_totales = []
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    driver = webdriver.Chrome(options=options)
    url_base = f"{URL}/{str.lower(ubicacion).replace(' ', '-')}/trabajo-{tematica}"
    Flitro_salarios = "?Salaries=menos-1-millon:1-15-millones:15-2-millones:2-25-millones:25-3-millones:3-35-millones:35-4-millones"
    Wait_10_secs = WebDriverWait(driver, 10)

    while pagina <= numero_paginas:

        if pagina == 1:
            url_final = f"{url_base}{Flitro_salarios}"
        else:
            print(f"Scrap page: {pagina}")
            url_final = f"{url_base}/{pagina}{Flitro_salarios}"
            print(url_final)
        driver.get(url_final)

        xpath_0_resultados = "//*[contains(text(), 'Tenemos cero ofertas')]"
        tarjeta_0_resultados = driver.find_elements(By.XPATH, xpath_0_resultados)

        if len(tarjeta_0_resultados) > 0:
            print(f"No hay vacantes para {tematica} en {ubicacion} para la página {pagina}")
            break
    
        try:
            Path_vacantes = "//div[contains(@class, 'area-bind')]"
            Wait_10_secs.until(
                EC.element_to_be_clickable((By.XPATH, Path_vacantes))
            )
            vacantes_totales = driver.find_elements(By.XPATH, Path_vacantes)
            
            try:
                for vacante in vacantes_totales:
                    try:
                        link_vacante = vacante.get_attribute("data-url")
                        link_info_vacante = f"https://www.elempleo.com{link_vacante}"

                        try:
                            xpath_contrato = ".//div[contains(text(), 'Tipo de contrato')]/preceding-sibling::div"
                            tipo_contrato = vacante.find_element(By.XPATH, xpath_contrato).text.strip()
                        except:
                            tipo_contrato = "No especificado"

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
                            
                    except Exception as error:
                        print(f"Ejecución detenida al procesar la vacante individual: {error}")
                        break

                pagina += 1            
            except Exception as error:
                print(f"Ejecución detenida al iterar por las vacantes: {error}")
                break
        except Exception as error:
            print(f"Ejecución detenida al intentar cargar ofertas de la página {pagina}: {error}")
            break

    driver.quit()
    
    if not datos_totales:
        return pd.DataFrame()
        
    CSV = pd.DataFrame(datos_totales)
    CSV = CSV[CSV['Salario'] != "Salario confidencial"]
    CSV = CSV.drop_duplicates()
    CSV['Programa_Asociado'] = tematica

    return CSV

scope = ["https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive"]

Credenciales = ServiceAccountCredentials.from_json_keyfile_name("applied-plexus-476714-n0-d7c1f0400cc6.json", scope)
client = gspread.authorize(Credenciales) 
load_dotenv(override=True)

Documento = os.getenv("Sheets_ECO")
Hoja_de_Trabajo = client.open_by_key(Documento).worksheet("SEGUIMIENTO")
datos = Hoja_de_Trabajo.get_all_values()
df = pd.DataFrame(datos[2:], columns=datos[1])

columnas_necesarias = ['Programa', 'Ciudad']
df_data_vacantes = df[columnas_necesarias].copy()
df_data_vacantes = df_data_vacantes.dropna(subset='Ciudad')
df_data_vacantes = df_data_vacantes.drop_duplicates()
df_data_vacantes["Programa"] = (df_data_vacantes["Programa"]
                    .str.strip()
                    .str.replace(r"T\.L\.?", "", regex=True)
                    .str.replace(r"^\s*en\s+", "", regex=True)
                    .str.replace(r"^\.\s*", "", regex=True)
                    .str.strip())
df_data_vacantes['Programa'] = df_data_vacantes['Programa'].replace('', pd.NA)
df_data_vacantes = df_data_vacantes.dropna(subset='Programa')
print(df_data_vacantes)

lista_resultados = []

for indice, fila in df_data_vacantes.iterrows():
    ciudad = fila['Ciudad']
    programa = fila['Programa']
    print(f"Extrayendo data de {programa} en {ciudad}")
    df_temporal = extraccion_vacantes(programa, 7, ciudad)

    if not df_temporal.empty:
        lista_resultados.append(df_temporal)

if not lista_resultados:
    sys.exit("Ejecución detenida")

vacantes = pd.concat(lista_resultados, ignore_index=True)
print(vacantes)

def descripcion_vacantes(CSV: pd.DataFrame):
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    driver = webdriver.Chrome()#(options=options)
    Wait_10_Sec = WebDriverWait(driver, 10)

    for indice, fila in CSV.iterrows():
        try:
            url_vacante = fila['Link_Oferta']       
            driver.get(url_vacante)

            Path_bloque_descripcion = '//div[contains(@class, "description-block")]//p[contains(@class, "mb-0")]'

            Descripcion = Wait_10_Sec.until(
                EC.presence_of_element_located(
                    (By.XPATH, Path_bloque_descripcion)
                )
            )

            Descripcion_value = Descripcion.text

            try: 
                Nivel_educativo = Wait_10_Sec.until(
                    EC.presence_of_element_located(
                        (By.XPATH, '//span[contains(text(), "Nivel educativo")]/preceding-sibling::span')
                    )
                )

                Nivel = Nivel_educativo.text

            except Exception as e:
                Nivel = 'Sin información'

            Fecha_publicacion_vacante = Wait_10_Sec.until(
                EC.presence_of_element_located(
                    (By.XPATH, '//p[contains(@class, "publish-date-info")]')
                )
            )

            texto_fecha = Fecha_publicacion_vacante.text.replace("Publicado", "").strip()
            fecha_parseada = dateparser.parse(texto_fecha)
            
            Fecha_publicacion = fecha_parseada.strftime('%Y-%m-%d')

            CSV.at[indice, 'Descripción'] = Descripcion_value
            CSV.at[indice, 'Nivel'] = Nivel
            CSV.at[indice, 'Fecha Publicación'] = Fecha_publicacion

            print(CSV.loc[indice])
            
        except Exception as error:
            print(f"Ejecución detenida en descripción de la vacante {url_vacante}: {error}")
            break
   
    driver.quit()

    if 'Descripción' in CSV.columns:
        CSV = CSV.dropna(subset=['Descripción'])
        
    if not CSV.empty:
        CSV['Fecha Publicación'] = pd.to_datetime(CSV['Fecha Publicación'], errors='coerce').dt.strftime('%Y-%m-%d')
        CSV = CSV[CSV['Nivel'].str.contains(r't[eé]cnic[oa]|media|bachi', case=False, na=False)]
        CSV = CSV[~CSV['Descripción'].str.contains(r"discapacidad|inclusi[oó]n", case=False, na=False)]
        CSV = CSV.sort_values(by='Fecha Publicación', ascending=False)
    
    return CSV

Datos_Vacantes_Seleccionadas = descripcion_vacantes(vacantes)

if Datos_Vacantes_Seleccionadas.empty:
    sys.exit("Ejecución detenida global: Las vacantes descritas quedaron vacías tras los filtros o errores. Se aborta la actualización para proteger el histórico.")

print(Datos_Vacantes_Seleccionadas)
Hoja_de_vacantes = client.open_by_key(Documento).worksheet("VACANTES")
Documento_Final = Datos_Vacantes_Seleccionadas.to_csv("Vacantes_ECO.csv", index=False)
datos_vacantes_previas = Hoja_de_vacantes.get_values("A:K")
df_vacantes_previas = pd.DataFrame(datos_vacantes_previas[1:], columns=datos_vacantes_previas[0])

Datos_Vacantes_Seleccionadas = Datos_Vacantes_Seleccionadas.reset_index(drop=True)
df_vacantes_previas = df_vacantes_previas.reset_index(drop=True)

columnas_estrictas = ["Vacante", "Empresa", "Ubicación", "Cargo_Equivalente", "Tipo_Contrato", "Salario", "Link_Oferta", "Programa_Asociado", "Descripción", "Nivel", "Fecha Publicación"]
Datos_Vacantes_Seleccionadas = Datos_Vacantes_Seleccionadas[columnas_estrictas]

Datos_Vacantes_Seleccionadas = pd.concat([Datos_Vacantes_Seleccionadas, df_vacantes_previas], ignore_index=True)
Datos_Vacantes_Seleccionadas = Datos_Vacantes_Seleccionadas.fillna("")

Datos_Vacantes_Seleccionadas = Datos_Vacantes_Seleccionadas.drop_duplicates(subset='Link_Oferta')
Datos_Vacantes_Seleccionadas = Datos_Vacantes_Seleccionadas.sort_values(by=['Ubicación', 'Programa_Asociado', 'Fecha Publicación'], ascending=[False, False, False])
CSV_TO_SHEETS = [Datos_Vacantes_Seleccionadas.columns.values.tolist()] + Datos_Vacantes_Seleccionadas.values.tolist()
_ = Hoja_de_vacantes.batch_clear(["A1:K"])
_ = Hoja_de_vacantes.update(range_name="A1:K", values= CSV_TO_SHEETS)