"""
Servicio de PDF + túnel de Cloudflare para flujos de n8n del proyecto EFE / Suba (nov-2026).

Funciones que usa pdf_bajo_demanda.py (en GitHub Actions, lanzado desde el Panel):
  1. iniciar_servicio(): levanta el servicio de PDF (FastAPI, main.py) en el puerto 8000.
  2. iniciar_tunel(): abre un quick tunnel de Cloudflare y espera a que su URL exista en el DNS público.
  3. actualizar_n8n(url, flujo): pone {url}/crear-pdf en los nodos HTTP del flujo que llaman a /crear-pdf
     (por la API de n8n; guarda un respaldo del flujo antes de cambiarlo, en EFE/logs/, excluida de git).
Copia adaptada de STC3.0-automatizaciones/Evidencias_remisiones/tunel_pdf.py.

Configuración: N8N_API_URL y N8N_API_KEY del .env de EFE (en Actions llega por SECRETS_BUNDLE).
Opcional: PDF_PUERTO. Prueba local (abre el túnel y lo mantiene): python tunel_pdf.py <ID_del_flujo>
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import requests

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
LOGS = RAIZ / "logs"  # carpeta ya excluida de git (.gitignore de EFE)
LOGS.mkdir(exist_ok=True)
LOG = LOGS / "tunel_pdf.log"
PATRON_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
               "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
               "executionOrder", "callerPolicy", "callerIds", "timeSavedPerExecution"}
SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # en Windows no abre consolas extra


def log(msg: str) -> None:
    linea = f"{datetime.now():%Y-%m-%d %H:%M:%S} · {msg}"
    print(linea, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(linea + "\n")


def _env(clave: str) -> str:
    if os.getenv(clave):
        return os.getenv(clave, "").strip()
    for archivo in (RAIZ / ".env",):
        if archivo.exists():
            for linea in archivo.read_text(encoding="utf-8-sig").splitlines():
                if "=" in linea and not linea.lstrip().startswith("#"):
                    k, v = linea.split("=", 1)
                    if k.strip() == clave:
                        return v.split(" #")[0].strip().strip('"').strip("'")
    return ""


API = _env("N8N_API_URL").rstrip("/")
KEY = _env("N8N_API_KEY")
FLUJO = _env("N8N_FLUJO_PDF") or (sys.argv[1] if len(sys.argv) > 1 and __name__ == "__main__" else "")
PUERTO = int(_env("PDF_PUERTO") or 8000)
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json"}


def _sesion_api() -> requests.Session:
    """Llamadas a la API de n8n con reintentos. nov-2026: n8n a veces tarda más de 60 s en responder (servidor
    ocupado) y el script caía con «Read timed out». Ahora: hasta 4 reintentos con espera creciente (5, 10, 20 s…)
    ante timeouts, cortes de conexión y errores 429/5xx. Solo para la API (no para el webhook, que no se repite)."""
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    s = requests.Session()
    reintentos = Retry(total=4, connect=4, read=4, status=4, backoff_factor=5,
                       status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset({"GET", "PUT", "POST"}),
                       raise_on_status=False)
    s.mount("https://", HTTPAdapter(max_retries=reintentos))
    s.mount("http://", HTTPAdapter(max_retries=reintentos))
    return s


API_HTTP = _sesion_api()
TIEMPO_API = 90


# ------------------------------------------------------------------ procesos
def _drenar(proc: subprocess.Popen, prefijo: str, al_leer=None) -> None:
    """Lee la salida del proceso (si no se lee, el proceso se bloquea) y la manda al log."""
    for linea in proc.stdout:
        linea = linea.rstrip()
        if al_leer:
            al_leer(linea)
        if any(p in linea for p in ("ERR", "error", "Error", "trycloudflare", "running on", "Uvicorn", "[crear-pdf]",
                                    "Traceback", "Exception")):
            log(f"{prefijo} {linea[:300]}")


def iniciar_servicio() -> subprocess.Popen:
    cmd = [sys.executable, "-m", "uvicorn", "main:app", "--app-dir", str(AQUI),
           "--host", "127.0.0.1", "--port", str(PUERTO)]
    proc = subprocess.Popen(cmd, cwd=str(AQUI), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", creationflags=SIN_VENTANA)
    threading.Thread(target=_drenar, args=(proc, "[pdf]"), daemon=True).start()
    for _ in range(60):  # hasta 30 s
        try:
            if requests.get(f"http://127.0.0.1:{PUERTO}/docs", timeout=2).ok:
                log(f"Servicio de PDF arriba en el puerto {PUERTO}")
                return proc
        except requests.RequestException:
            pass
        if proc.poll() is not None:
            raise RuntimeError("El servicio de PDF se cerró al arrancar (revisa el log).")
        time.sleep(0.5)
    raise RuntimeError("El servicio de PDF no respondió en 30 s.")


def _cloudflared() -> str:
    for c in (shutil.which("cloudflared"),
              r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
              r"C:\Program Files\cloudflared\cloudflared.exe",
              str(Path.home() / "AppData/Local/Microsoft/WinGet/Links/cloudflared.exe")):
        if c and Path(c).exists():
            return c
    raise RuntimeError("No encontré cloudflared. Instálalo con: winget install Cloudflare.cloudflared")


def iniciar_tunel() -> tuple[subprocess.Popen, str]:
    hallada: dict[str, str] = {}
    listo = threading.Event()

    def buscar(linea: str) -> None:
        m = PATRON_URL.search(linea)
        if m and not listo.is_set():
            hallada["url"] = m.group(0)
            listo.set()

    # --protocol http2: usa TCP 443. El protocolo por defecto (QUIC/UDP) se corta en muchas redes
    # ("failed to accept QUIC stream: timeout") y n8n deja de poder llegar al servicio.
    proc = subprocess.Popen([_cloudflared(), "tunnel", "--no-autoupdate", "--protocol", "http2",
                             "--url", f"http://127.0.0.1:{PUERTO}"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                            errors="replace", creationflags=SIN_VENTANA)
    threading.Thread(target=_drenar, args=(proc, "[túnel]", buscar), daemon=True).start()
    if not listo.wait(60):
        proc.kill()
        raise RuntimeError("Cloudflare no entregó la URL del túnel en 60 s.")
    url = hallada["url"]
    # La URL nueva tarda en existir en el DNS público. Si se le pasa a n8n antes, n8n falla con
    # "The connection cannot be established… incorrect host". Se confirma con el DNS público de
    # Cloudflare (no con el de este PC, que puede guardar en caché el "no existe") y luego que responda.
    if not _resuelve(url, espera_max=180):
        proc.kill()
        raise RuntimeError(f"El DNS público no resolvió {url} en 3 min.")
    responde = any(_responde(url) or time.sleep(3) for _ in range(20))
    log(f"Túnel abierto: {url}" + ("" if responde else " (este PC aún no lo alcanza; el DNS público ya sí)"))
    return proc, url


def _resuelve(url: str, espera_max: int) -> bool:
    """True cuando el DNS público ya conoce la URL. Si la red no deja consultar el DNS de
    Cloudflare, se conforma con que la URL responda desde este PC."""
    host = url.split("//", 1)[1]
    fin, doh_ok = time.time() + espera_max, False
    while time.time() < fin:
        try:
            r = requests.get("https://cloudflare-dns.com/dns-query", params={"name": host, "type": "A"},
                             headers={"accept": "application/dns-json"}, timeout=10)
            doh_ok = doh_ok or r.ok
            if r.ok and r.json().get("Answer"):
                return True
        except (requests.RequestException, ValueError):
            if _responde(url):
                return True
        time.sleep(5)
    return not doh_ok  # sin DNS público disponible: se sigue (con aviso en el log)


def _responde(url: str) -> bool:
    try:
        return requests.get(f"{url}/docs", timeout=10).ok
    except requests.RequestException:
        return False


# ------------------------------------------------------------------ n8n
# Hosts de túneles temporales: un nodo HTTP que apunte a uno de estos también se actualiza, aunque su ruta no sea
# exactamente /crear-pdf (se conserva la ruta y se cambia solo el dominio).
TUNELES = re.compile(r"https?://[^/\s\"']*(trycloudflare\.com|pinggy[^/\s\"']*|ngrok[^/\s\"']*|loca\.lt|serveo\.net)",
                     re.IGNORECASE)


def _es_nodo_pdf(n: dict) -> bool:
    url = str(n.get("parameters", {}).get("url", ""))
    return n.get("type", "").endswith(".httpRequest") and ("/crear-pdf" in url or bool(TUNELES.search(url)))


def _url_nueva(actual: str, url_tunel: str) -> str:
    """Misma ruta, dominio del túnel nuevo. Sin dominio de túnel reconocible → {túnel}/crear-pdf."""
    m = TUNELES.search(actual)
    if m:
        ruta = actual[m.end():].split("?")[0].strip() or "/crear-pdf"
        return f"{url_tunel}{ruta if ruta.startswith('/') else '/' + ruta}"
    return f"{url_tunel}/crear-pdf"


def _activar(flujo: str) -> dict:
    """Activa el flujo (el webhook de producción solo existe si está activo) y comprueba que quedó activo."""
    a = API_HTTP.post(f"{API}/workflows/{flujo}/activate", headers=H, timeout=TIEMPO_API)
    if not a.ok:
        raise RuntimeError(f"n8n no pudo activar el flujo (HTTP {a.status_code}): {a.text[:300]}")
    estado = API_HTTP.get(f"{API}/workflows/{flujo}", headers=H, timeout=TIEMPO_API).json()
    if not estado.get("active"):
        raise RuntimeError("n8n respondió a la activación pero el flujo sigue inactivo: actívalo a mano en el editor "
                           "y revisa si muestra algún error de activación.")
    return estado


def actualizar_n8n(url_tunel: str, flujo: str | None = None) -> None:
    """Pone la URL del túnel en todos los nodos HTTP del flujo que llaman al servicio de PDF y COMPRUEBA que n8n
    guardó el cambio. nov-2026: antes, si n8n rechazaba el cambio solo se anotaba en el log y el flujo corría con la
    URL vieja («The connection cannot be established… incorrect host»). Ahora cualquier falla detiene la ejecución
    con el motivo, antes de disparar el flujo."""
    flujo = flujo or FLUJO
    if not (API and KEY):
        raise RuntimeError("Faltan N8N_API_URL / N8N_API_KEY: no se puede poner la URL del túnel en n8n.")
    r = API_HTTP.get(f"{API}/workflows/{flujo}", headers=H, timeout=TIEMPO_API)
    if not r.ok:
        raise RuntimeError(f"n8n no entregó el flujo {flujo} (HTTP {r.status_code}): {r.text[:200]}. "
                           "Revisa que la N8N_API_KEY pueda ver y editar este flujo.")
    wf = r.json()
    nodos = [n for n in wf["nodes"] if _es_nodo_pdf(n)]
    if not nodos:
        raise RuntimeError(f"El flujo «{wf.get('name')}» no tiene nodos HTTP que llamen al servicio de PDF.")
    esperadas, cambios = {}, []
    for n in nodos:
        p = n["parameters"]
        nueva = _url_nueva(str(p["url"]), url_tunel)
        esperadas[n["name"]] = nueva
        if p["url"] != nueva:
            cambios.append(f"«{n['name']}»")
            p["url"] = nueva
    if cambios:
        respaldo = LOGS / f"respaldo_flujo_pdf_{flujo}_{datetime.now():%Y%m%d_%H%M%S}.json"
        respaldo.write_text(json.dumps(wf, ensure_ascii=False), encoding="utf-8")
        cuerpo = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
                  "settings": {k: v for k, v in (wf.get("settings") or {}).items() if k in SETTINGS_OK}}
        r = API_HTTP.put(f"{API}/workflows/{flujo}", headers={**H, "Content-Type": "application/json"},
                         data=json.dumps(cuerpo), timeout=TIEMPO_API)
        if not r.ok:
            raise RuntimeError(f"n8n rechazó el cambio de URL (HTTP {r.status_code}): {r.text[:300]}")
        # Que la versión ACTIVA (la que atiende el webhook) sea la recién guardada. nov-2026: desactivar y volver a
        # activar dejaba el webhook sin registrar unos segundos (n8n respondía 404 «webhook is not registered»), así
        # que solo se activa encima (publica la versión nueva) y únicamente si n8n reporta otra versión activa se hace
        # el ciclo completo. disparar_webhook() además reintenta si el webhook aún no está registrado.
        estado = _activar(flujo)
        if estado.get("activeVersionId") and estado.get("activeVersionId") != estado.get("versionId"):
            API_HTTP.post(f"{API}/workflows/{flujo}/deactivate", headers=H, timeout=TIEMPO_API)
            _activar(flujo)
    elif not wf.get("active"):
        _activar(flujo)  # sin cambios de URL pero apagado: el webhook del panel solo existe con el flujo activo
    # Comprobación: se vuelve a leer el flujo y cada nodo debe tener la URL del túnel nuevo.
    r = API_HTTP.get(f"{API}/workflows/{flujo}", headers=H, timeout=TIEMPO_API)
    r.raise_for_status()
    guardado = {n["name"]: str(n.get("parameters", {}).get("url", "")) for n in r.json()["nodes"]}
    mal = [nombre for nombre, url in esperadas.items() if guardado.get(nombre) != url]
    if mal:
        raise RuntimeError(f"n8n no guardó la URL del túnel en: {', '.join(mal)}.")
    log(f"✔ n8n actualizado ({wf['name']}): {len(esperadas)} nodos de PDF → {url_tunel}"
        + (f" (cambiados: {', '.join(cambios)})" if cambios else " (ya la tenían)"))
    # Respaldos viejos: se conservan los 5 más recientes.
    for viejo in sorted(LOGS.glob("respaldo_flujo_pdf_*.json"))[:-5]:
        viejo.unlink(missing_ok=True)


# ------------------------------------------------------------------ ciclo principal
def main() -> None:
    if not FLUJO:
        sys.exit("Indica el ID del flujo de n8n: python tunel_pdf.py <ID>  (o N8N_FLUJO_PDF en el .env)")
    log("=== Inicio del túnel de PDF ===")
    servicio = tunel = None
    url, fallos = "", 0
    try:
        while True:
            if servicio is None or servicio.poll() is not None:
                if servicio is not None:
                    log("⚠ El servicio de PDF se cayó; reiniciando…")
                servicio = iniciar_servicio()
            if tunel is not None and tunel.poll() is None:
                # El proceso puede seguir vivo con el túnel muerto: se prueba la URL pública.
                fallos = 0 if _responde(url) else fallos + 1
                if fallos >= 3:  # ~3 min sin respuesta
                    log("⚠ El túnel no responde hace 3 min; abriendo uno nuevo…")
                    tunel.kill()
            if tunel is None or tunel.poll() is not None:
                if tunel is not None:
                    log("⚠ El túnel se cerró; abriendo uno nuevo…")
                tunel, url = iniciar_tunel()
                fallos = 0
                actualizar_n8n(url)
            time.sleep(60)
    except KeyboardInterrupt:
        log("Detenido por el usuario (Ctrl+C).")
    except Exception as exc:  # noqa: BLE001 -- dejar rastro en el log y reintentar desde el programador
        log(f"✖ Error: {exc}")
        raise
    finally:
        for p in (tunel, servicio):
            if p and p.poll() is None:
                p.terminate()


if __name__ == "__main__":
    main()
