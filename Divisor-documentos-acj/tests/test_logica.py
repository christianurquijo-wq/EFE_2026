"""
Pruebas de la lógica que no depende de Google Drive: división de PDF y
lectura/normalización de cédulas. Se corren con: python -m pytest tests/
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
from pypdf import PdfWriter

from src.cedulas import leer_cedulas
from src.pdf_utils import PDFInvalidoError, dividir_pdf


def _crear_pdf_prueba(ruta: str, num_paginas: int):
    writer = PdfWriter()
    for _ in range(num_paginas):
        writer.add_blank_page(width=612, height=792)
    with open(ruta, "wb") as f:
        writer.write(f)


def test_division_5_paginas(tmp_path):
    origen = tmp_path / "123456789_001AcuerdoCompromiso.pdf"
    _crear_pdf_prueba(str(origen), 5)

    acj = tmp_path / "123456789_ACJ.pdf"
    cc = tmp_path / "123456789_CC.pdf"
    resultado = dividir_pdf(str(origen), str(acj), str(cc))

    assert resultado.total_paginas == 5
    assert resultado.advertencia is None

    from pypdf import PdfReader
    assert len(PdfReader(str(acj)).pages) == 4
    assert len(PdfReader(str(cc)).pages) == 1


def test_division_ignora_paginas_extra(tmp_path):
    origen = tmp_path / "999_001AcuerdoCompromiso.pdf"
    _crear_pdf_prueba(str(origen), 8)  # PDF con más de 5 páginas

    acj = tmp_path / "999_ACJ.pdf"
    cc = tmp_path / "999_CC.pdf"
    resultado = dividir_pdf(str(origen), str(acj), str(cc))

    assert resultado.total_paginas == 8
    assert resultado.advertencia is None

    from pypdf import PdfReader
    assert len(PdfReader(str(acj)).pages) == 4
    assert len(PdfReader(str(cc)).pages) == 1


def test_division_pdf_una_sola_pagina_falla(tmp_path):
    origen = tmp_path / "1_001AcuerdoCompromiso.pdf"
    _crear_pdf_prueba(str(origen), 1)

    acj = tmp_path / "1_ACJ.pdf"
    cc = tmp_path / "1_CC.pdf"

    try:
        dividir_pdf(str(origen), str(acj), str(cc))
        assert False, "Se esperaba PDFInvalidoError"
    except PDFInvalidoError:
        pass


def test_leer_cedulas_desde_csv(tmp_path):
    ruta = tmp_path / "lista.csv"
    ruta.write_text("cedula\n123456789\n987654321.0\n  111.222.333 \n123456789\n")

    cedulas = leer_cedulas(str(ruta))
    assert cedulas == ["123456789", "987654321", "111222333"]


def test_leer_cedulas_columna_sin_nombre_estandar(tmp_path):
    ruta = tmp_path / "lista2.xlsx"
    df = pd.DataFrame({"Numero de Documento": ["1010101010", "2020202020"]})
    df.to_excel(ruta, index=False)

    cedulas = leer_cedulas(str(ruta))
    assert cedulas == ["1010101010", "2020202020"]
