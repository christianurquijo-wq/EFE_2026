import subprocess
import sys

scripts_ejecutables = ["bitacora_ECO.py", "bitacora_JAE.py"]

print(f"Ejecutando los siguientes códigos: {scripts_ejecutables}. Total: {len(scripts_ejecutables)}")

Barra = "="*60
scrpits_fallidos = {}

for script in scripts_ejecutables:
    try:
        print(f"\n\nIniciando ejecución: {script}")
        subprocess.run([sys.executable, script], check=True)
        print(f"{script} ejecutado correctamente")
    except subprocess.CalledProcessError as error:
        print(f"Hubo un problema con la ejecución del script '{script}' asociado a {error}")
        scrpits_fallidos[script] = str(error)
        continue

if len(scrpits_fallidos) == 0:
    print("Actualización total de los scripts")
else:
    print(f"Actualización finalizada pero hubo un problema con los siguientes scripts. Total fallas {len(scrpits_fallidos)}") 
    for fallido, detalle in scrpits_fallidos.items():
        print(f" - {fallido}: {detalle}")