"""
Corre un flujo de n8n que genera PDF por /crear-pdf, con el servicio de PDF y el túnel BAJO DEMANDA (nov-2026):
el servicio y el túnel existen solo mientras corre el flujo y no dependen del PC de nadie.

ejecutar(flujo, minutos, …), en GitHub Actions (ops_run_script.yml, lanzado desde el Panel):
  1. Levanta el servicio de PDF (main.py, Playwright) en el runner.
  2. Abre un túnel de Cloudflare (quick tunnel) y espera a que su URL exista en el DNS público.
  3. Pone esa URL en los nodos HTTP del flujo que llaman a /crear-pdf (tunel_pdf.actualizar_n8n).
  4. Dispara el flujo por su webhook y espera a que la ejecución termine (consulta la API de n8n).
  5. Cierra el túnel y el servicio. Verde si el flujo terminó bien; si no, rojo con el nodo que falló.
Misma rutina que Remisiones de STC 3.0 (STC3.0-automatizaciones/Evidencias_remisiones).
"""
from __future__ import annotations

import os
import platform
import shutil
import stat
import sys
import time
from pathlib import Path

import requests

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import tunel_pdf as t  # noqa: E402  (mismas funciones del túnel local: servicio, túnel, actualizar n8n)

FINALES = {"success", "error", "crashed", "canceled"}
URL_CLOUDFLARED = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"


def asegurar_cloudflared() -> None:
    """En el runner de GitHub (Linux) no viene instalado: se descarga el binario oficial."""
    if shutil.which("cloudflared") or platform.system() != "Linux":
        return
    destino = Path(os.getenv("RUNNER_TEMP", "/tmp")) / "cloudflared"
    if not destino.exists():
        t.log("Descargando cloudflared…")
        r = requests.get(URL_CLOUDFLARED, timeout=120)
        r.raise_for_status()
        destino.write_bytes(r.content)
        destino.chmod(destino.stat().st_mode | stat.S_IEXEC)
    os.environ["PATH"] = f"{destino.parent}{os.pathsep}{os.environ.get('PATH', '')}"


def ultima_ejecucion(flujo: str) -> int:
    r = requests.get(f"{t.API}/executions", headers=t.H, params={"workflowId": flujo, "limit": 1}, timeout=60)
    r.raise_for_status()
    datos = r.json().get("data", [])
    return int(datos[0]["id"]) if datos else 0


def _cabeceras(prefijo: str) -> list[dict]:
    """Cabeceras a probar, en orden. El webhook usa la credencial «OPS X-OPS-TOKEN» (la del Panel):
    1) la configurada en el .env (<prefijo>_HEADER_NOMBRE / _VALOR); 2) X-OPS-TOKEN con OPS_ALERT_TOKEN, el token que el runner ya
    recibe para las alertas (mismo valor que n8n_token del dashboard)."""
    nombre, valor = t._env(f"{prefijo}_HEADER_NOMBRE"), t._env(f"{prefijo}_HEADER_VALOR")
    opciones = [{nombre: valor}] if nombre and valor else []
    if os.getenv("OPS_ALERT_TOKEN"):
        opciones.append({"X-OPS-TOKEN": os.environ["OPS_ALERT_TOKEN"]})
    return opciones or [{}]


def disparar_webhook(url: str | None, prefijo: str, origen: str, nombre: str) -> None:
    url = url or t._env(f"{prefijo}_URL")
    if not url:
        raise RuntimeError(f"Falta la URL del webhook ({prefijo}_URL en el .env).")
    cuerpo = {"origen": origen, "request_id": os.getenv("OPS_REQUEST_ID", ""),
              "actor": os.getenv("OPS_ACTOR", "")}
    r = None
    for cab in _cabeceras(prefijo):
        try:
            r = requests.post(url, headers=cab, json=cuerpo, timeout=30)
        except requests.ReadTimeout:
            break  # el webhook puede responder al final del flujo: la ejecución sigue en n8n
        if r.status_code not in (401, 403):
            break  # con 401/403 se prueba la siguiente cabecera
    if r is not None and r.status_code >= 400:
        pista = ""
        if r.status_code in (401, 403):
            probadas = ", ".join(next(iter(c), "sin cabecera") for c in _cabeceras(prefijo))
            pista = (f" · Cabeceras probadas: {probadas}. El valor debe ser el mismo de la credencial «OPS X-OPS-TOKEN» "
                     "de n8n (el n8n_token del panel): secret OPS_ALERT_TOKEN del repo o "
                     f"{prefijo}_HEADER_NOMBRE / _VALOR en el .env.")
        raise RuntimeError(f"n8n {r.status_code}: {r.text[:300]}{pista}")
    t.log(f"Flujo de {nombre} disparado en n8n.")


def esperar(base: int, minutos: int, flujo: str) -> dict:
    """Espera a que aparezca la ejecución nueva (id > base) y termine."""
    fin = time.time() + minutos * 60
    ejecucion = None
    while time.time() < fin:
        r = requests.get(f"{t.API}/executions", headers=t.H,
                         params={"workflowId": flujo, "limit": 5}, timeout=60)
        if r.ok:
            nuevas = [e for e in r.json().get("data", []) if int(e["id"]) > base]
            if nuevas:
                ejecucion = min(nuevas, key=lambda e: int(e["id"]))
                if str(ejecucion.get("status")) in FINALES or ejecucion.get("finished"):
                    return ejecucion
        time.sleep(20)
    raise RuntimeError(f"TIMEOUT: el flujo no terminó en {minutos} min"
                       + (f" (ejecución {ejecucion['id']} sigue en n8n)" if ejecucion else ""))


def error_de(eid: str, estado: str) -> str:
    try:
        r = requests.get(f"{t.API}/executions/{eid}", headers=t.H, params={"includeData": "true"}, timeout=60)
        res = ((r.json().get("data") or {}).get("resultData") or {}) if r.ok else {}
    except requests.RequestException:
        res = {}
    err = res.get("error") or {}
    nodo = err.get("node", {}).get("name") if isinstance(err.get("node"), dict) else err.get("node")
    msg = err.get("message") or err.get("description") or f"n8n status: {estado}"
    # nov-2026: n8n a veces deja el error general sin nodo (p. ej. solo «aborted»). Se buscan los nodos que
    # fallaron en runData y el último nodo ejecutado, para que la alerta diga dónde se rompió.
    fallidos = []
    for nombre, corridas in (res.get("runData") or {}).items():
        for c in corridas or []:
            e = c.get("error") if isinstance(c, dict) else None
            if e:
                detalle = e.get("description") or e.get("message") or ""
                codigo = e.get("httpCode") or (e.get("context") or {}).get("httpCode") or ""
                fallidos.append(f"«{nombre}»" + (f" HTTP {codigo}" if codigo else "") + f": {str(detalle)[:200]}")
    ultimo = res.get("lastNodeExecuted")
    texto = (f"Nodo «{nodo}»: " if nodo else "") + str(msg)
    if fallidos:
        texto += " · Nodos con error: " + " | ".join(fallidos[:3])
    elif ultimo and not nodo:
        texto += f" · Último nodo ejecutado: «{ultimo}»"
    return texto[:800]


def ejecutar(flujo: str, minutos: int, *, webhook_url: str | None, prefijo: str, origen: str, nombre: str) -> None:
    """Servicio de PDF + túnel → URL en los nodos /crear-pdf del flujo → webhook → espera → cierre."""
    if not (t.API and t.KEY):
        sys.exit("Faltan N8N_API_URL / N8N_API_KEY en el .env de EFE.")
    servicio = tunel = None
    try:
        asegurar_cloudflared()
        servicio = t.iniciar_servicio()
        tunel, url = t.iniciar_tunel()
        t.actualizar_n8n(url, flujo)
        base = ultima_ejecucion(flujo)
        disparar_webhook(webhook_url, prefijo, origen, nombre)
        e = esperar(base, minutos, flujo)
        estado = str(e.get("status"))
        if estado != "success":
            sys.exit(error_de(str(e["id"]), estado))
        t.log(f"✔ {nombre} terminó bien (ejecución {e['id']} de n8n).")
    finally:
        for p in (tunel, servicio):
            if p and p.poll() is None:
                p.terminate()
        t.log("Túnel y servicio de PDF cerrados.")
