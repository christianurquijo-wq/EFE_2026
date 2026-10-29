
import os
import glob
import sys

# oct-2026 (panel de operaciones): cada script se ejecuta a través de
# ops_logger, que deja una fila por script en LOG_EJECUCIONES y avisa fallos.
# La lógica de selección (exclusiones + Mantenimiento_appends primero) NO cambia.
from ops_logger import ejecutar, alertar_resumen

scripts_listados = sorted(glob.glob("*.py"))

archivos_excluidos = ['trigger.py',
                      'ops_logger.py',          # ejecutor/bitácora, no es un ETL
                      'ops_sync_n8n.py',        # sync de n8n: tiene su propio workflow (cada hora)
                      'trigger_bitacora.py',    # las bitácoras ya corren aquí directo; antes se ejecutaban 2 veces
                      'Append Colsubsidio2026.py',
                      'Formacion InAv Suba2026.py',
                      'Formacion basico Suba2026.py',
                      'GenerarDashEco.py',
                      'Limpieza_caracterizacion.py',
                      'Limpieza_empleabilidad.py',
                      'Limpieza_satisfaccion.py',
                      'DashEco.py',
                      'validacion_dataframes.py',
                      'Limpieza_seguimiento.py',
                      'Append_DATA_BQ.py',
                      'colsu2.py',
                      'STC_3_0_FCS.py'
                      #'Caracterizacion Colsubsidio2026.py',
                      #'Satisfaccion_Colsubsidio2026.py',
                      #'Upload Colsubsidio2026.py',
                      ]

script_prioridad = 'Mantenimiento_appends.py'
# oct-2026: la foto diaria (historial para KPIs por día/semana/mes) va DE ÚLTIMA,
# cuando todas las tablas Unificado_* ya quedaron actualizadas esa noche.
script_final = 'Foto_diaria_EFE.py'

# oct-2026: BigQuery está en sandbox y borra tablas Y VISTAS a los 60 días. Antes que nada
# se les extiende la vigencia (las vistas Unificado_* no tenían ningún respaldo).
script_vigencia = 'Vigencia_sandbox.py'

scripts_ejecutables = [script_vigencia] if os.path.exists(script_vigencia) else []
scripts_ejecutables.append(script_prioridad)
for script in scripts_listados:
    if script not in archivos_excluidos and script not in (script_prioridad, script_final, script_vigencia):
        scripts_ejecutables.append(script)
if os.path.exists(script_final):
    scripts_ejecutables.append(script_final)

print(f"Ejecutando los siguientes códigos: {scripts_ejecutables}. Total: {len(scripts_ejecutables)}")

LOTE = os.getenv("OPS_LOTE", "nocturno")
Barra = "="*60
scrpits_fallidos = []
for script in scripts_ejecutables:
    if script == script_prioridad:
        print(f"{Barra}\nAPPEND\n{Barra}")
    resultado = ejecutar(script, lote=LOTE, timeout_min=30, alertar=False)
    if resultado["estado"] != "EXITOSO":
        scrpits_fallidos.append(resultado)

if len(scrpits_fallidos) == 0:
    print("Actualización total de los scripts")
else:
    print(f"Actualización finalizada pero hubo un problema con los siguientes scripts. Total fallas {len(scrpits_fallidos)}")
    for fallido in scrpits_fallidos:
        print(f" - {fallido['script']}: {fallido['estado']}")
    alertar_resumen(LOTE, scrpits_fallidos)
    # Antes el job siempre terminaba en verde aunque fallaran scripts.
    # Ahora queda en rojo en GitHub para que el fallo sea visible.
    sys.exit(1)
