"""
Utilidades para dividir el PDF de cada participante en ACJ (Acuerdo de
Compromiso) y CC (documento de identidad).
"""

from dataclasses import dataclass

from pypdf import PdfReader, PdfWriter


class PDFInvalidoError(Exception):
    """Se lanza cuando el PDF de origen no tiene la estructura esperada."""


@dataclass
class ResultadoDivision:
    ruta_acj: str
    ruta_cc: str
    total_paginas: int
    advertencia: str | None = None


def dividir_pdf(ruta_entrada: str, ruta_salida_acj: str, ruta_salida_cc: str) -> ResultadoDivision:

    reader = PdfReader(ruta_entrada)
    total_paginas = len(reader.pages)

    if total_paginas < 5:
        raise PDFInvalidoError(
            f"El PDF solo tiene {total_paginas} página(s); se necesitan al menos 5 "
            "(4 del ACJ + 1 del documento de identidad)."
        )

    escritor_acj = PdfWriter()
    for i in range(0, 4):  # páginas 1 a 4
        escritor_acj.add_page(reader.pages[i])
    with open(ruta_salida_acj, "wb") as f:
        escritor_acj.write(f)

    escritor_cc = PdfWriter()
    escritor_cc.add_page(reader.pages[4])  # página 5
    with open(ruta_salida_cc, "wb") as f:
        escritor_cc.write(f)

    return ResultadoDivision(
        ruta_acj=ruta_salida_acj,
        ruta_cc=ruta_salida_cc,
        total_paginas=total_paginas,
        advertencia=None,
    )