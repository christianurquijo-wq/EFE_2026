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


URL = "https://www.elempleo.com/co/ofertas-empleo"

def extraccion_vacantes(tematica, numero_paginas: int, ubicacion):

    pagina = 1
    datos_totales = []
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    driver = webdriver.Chrome(options=options)
    url_base = f"{URL}/{str.lower(ubicacion).replace(' ', '-')}/trabajo-{tematica}"
    Flitro_salarios = "?Salaries=menos-1-millon:1-15-millones:15-2-millones:2-25-millones:25-3-millones:3-35-millones:35-4-millones"

    while pagina <= numero_paginas:
        if pagina == 1:
           url_final = f"{url_base}{Flitro_salarios}"
        else:
            print(f"Scrap page: {pagina} ")
            url_final = f"{url_base}/{pagina}{Flitro_salarios}"
            print(url_final)
        driver.get(url_final)

        try:
            Wait_10_secs = WebDriverWait(driver, 10)

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
                        print(error)

                pagina += 1
                
            except Exception as error:
                print(error)
    
        except Exception as error:
            print(error)


    driver.quit()
    CSV = pd.DataFrame(datos_totales)
    CSV = CSV[CSV['Tipo_Contrato'] != 'Contrato de aprendizaje']
    CSV = CSV[CSV['Salario'] != "Salario confidencial"]
    CSV = CSV.drop_duplicates()
    CSV['Programa_Asociado'] = tematica

    return CSV

datos_mercadeo = extraccion_vacantes("Mercadeo y Ventas", 2, "Bogotá")
datos_administrativo = extraccion_vacantes("Auxiliar Administrativo", 2, "Bogotá")

scope = ["https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive"]

Credenciales = ServiceAccountCredentials.from_json_keyfile_name("applied-plexus-476714-n0-d7c1f0400cc6.json", scope)

client = gspread.authorize(Credenciales) 

load_dotenv(override=True)
Documento = os.getenv("Sheets_JAE")
Hoja_de_Trabajo = client.open_by_key(Documento).worksheet("VACANTES")

CSV_FINAL = pd.concat([datos_mercadeo, datos_administrativo[1:]], ignore_index=True)

def descripcion_vacantes(CSV: pd.DataFrame):
    options = webdriver.ChromeOptions()
    options = options.add_argument('--headless')
    driver = webdriver.Chrome(options=options)
    Wait_10_Sec = WebDriverWait(driver, 10)

    for indice, fila in CSV.iterrows():
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

        Fecha_publicacion = dateparser.parse(Fecha_publicacion_vacante.text.replace("Publicado",  "")).strftime('%Y-%m-%d')

        CSV.at[indice, 'Descripción'] = Descripcion_value
        CSV.at[indice, 'Nivel'] = Nivel
        CSV.at[indice, 'Fecha Publicación'] = Fecha_publicacion


        print(CSV.loc[indice])


    
    driver.quit()

    CSV['Fecha Publicación'] = pd.to_datetime(CSV['Fecha Publicación']).dt.strftime('%Y-%m-%d')
    CSV = CSV[CSV['Nivel'].str.contains(r't[eé]cnic[oa]|media|bachi', case=False, na=False)]

    CSV = CSV.sort_values(by='Fecha Publicación', ascending=False)
    
    return CSV

Datos_Vacantes_Seleccionadas = descripcion_vacantes(CSV_FINAL)
print(Datos_Vacantes_Seleccionadas)

Documento_Final = Datos_Vacantes_Seleccionadas.to_csv("Vacantes_Seleccionadas.csv", index=False)



CSV_TO_SHEETS = [Datos_Vacantes_Seleccionadas.columns.values.tolist()] + Datos_Vacantes_Seleccionadas.values.tolist()

Hoja_de_Trabajo.clear()

Hoja_de_Trabajo.update(range_name="A1", values= CSV_TO_SHEETS)



 