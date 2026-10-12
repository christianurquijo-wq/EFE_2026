import os
import sys

# oct-2026 (panel de operaciones): ejecución con bitácora y alertas vía ops_logger.
from ops_logger import ejecutar, alertar_resumen

scripts_ejecutables = ["bitacora_ECO.py", "bitacora_JAE.py"]

print(f"Ejecutando los siguientes códigos: {scripts_ejecutables}. Total: {len(scripts_ejecutables)}")

LOTE = os.getenv("OPS_LOTE", "bitacoras")
scrpits_fallidos = []

for script in scripts_ejecutables:
    resultado = ejecutar(script, lote=LOTE, timeout_min=15, alertar=False)
    if resultado["estado"] != "EXITOSO":
        scrpits_fallidos.append(resultado)

if len(scrpits_fallidos) == 0:
    print("Actualización total de los scripts")
else:
    print(f"Actualización finalizada pero hubo un problema con los siguientes scripts. Total fallas {len(scrpits_fallidos)}")
    for fallido in scrpits_fallidos:
        print(f" - {fallido['script']}: {fallido['estado']}")
    alertar_resumen(LOTE, scrpits_fallidos)
    sys.exit(1)
