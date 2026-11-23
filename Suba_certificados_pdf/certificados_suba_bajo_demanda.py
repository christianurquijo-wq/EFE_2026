"""
Suba · Certificados y satisfacción BAJO DEMANDA (nov-2026).

Flujo de n8n «EFE_SUBA_EnvioCertificadoYSatisfacciónFormación_GP_20260413». Sus nodos «Genera PDF5/6/7» llaman a
/crear-pdf por un túnel que antes se abría a mano (pinggy) y cambiaba de URL. Ahora el botón
«Suba · Certificados y satisfacción» del Panel corre este script en GitHub Actions (ops_run_script.yml) y hace lo
mismo que Remisiones de STC 3.0 (pdf_bajo_demanda.ejecutar):
  1. levanta el servicio de PDF (main.py) en el runner;
  2. abre un túnel de Cloudflare y espera a que su URL exista en el DNS público;
  3. pone esa URL en TODOS los nodos HTTP del flujo que llaman a /crear-pdf (guarda respaldo antes);
  4. dispara el flujo por su webhook del panel («suba-certificados-satisfaccion», cabecera X-OPS-TOKEN) y espera a
     que la ejecución termine;
  5. cierra túnel y servicio. Verde si n8n terminó bien; si no, rojo con el nodo que falló.

Configuración (EFE/.env, viaja en SECRETS_BUNDLE): N8N_API_URL y N8N_API_KEY (la key debe poder editar este flujo).
Opcionales: N8N_FLUJO_SUBA_CERTIFICADOS (ID; si no, se busca por nombre), WEBHOOK_SUBA_CERT_URL,
WEBHOOK_SUBA_CERT_HEADER_NOMBRE / _VALOR (si no, X-OPS-TOKEN con OPS_ALERT_TOKEN del runner) y
SUBA_CERT_TIMEOUT_MIN (por defecto 100; el timeout_min del CATALOGO debe ser mayor).
"""
from __future__ import annotations

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pdf_bajo_demanda as pbd  # noqa: E402
import tunel_pdf as t  # noqa: E402

NOMBRE_FLUJO = "EFE_SUBA_EnvioCertificadoYSatisfacciónFormación_GP_20260413"
ID_CONOCIDO = "iRwzfycCexLTxNvg"  # ID en n8n (nov-2026); si el flujo se copia o reimporta, cambia
WEBHOOK = "https://n8n.kuepa.com/webhook/suba-certificados-satisfaccion"


def id_del_flujo() -> str:
    """ID por variable de entorno; si no, se busca por nombre (al copiar un flujo su ID cambia)."""
    if t._env("N8N_FLUJO_SUBA_CERTIFICADOS"):
        return t._env("N8N_FLUJO_SUBA_CERTIFICADOS")
    try:
        r = requests.get(f"{t.API}/workflows", headers=t.H, params={"name": NOMBRE_FLUJO, "limit": 50}, timeout=60)
        if r.ok:
            candidatos = [w for w in r.json().get("data", []) if w.get("name") == NOMBRE_FLUJO]
            if candidatos:
                return max(candidatos, key=lambda w: str(w.get("updatedAt", "")))["id"]
    except requests.RequestException:
        pass
    return ID_CONOCIDO


def revisar(flujo: str) -> None:
    """python Suba_certificados_pdf/certificados_suba_bajo_demanda.py --revisar
    Muestra qué nodos de PDF detecta el script y la URL que tienen hoy en n8n (no cambia nada)."""
    r = requests.get(f"{t.API}/workflows/{flujo}", headers=t.H, timeout=60)
    print(f"Flujo {flujo}: HTTP {r.status_code}")
    if not r.ok:
        sys.exit(r.text[:300])
    wf = r.json()
    print(f"{wf.get('name')} · activo: {wf.get('active')}")
    for n in wf["nodes"]:
        if n.get("type", "").endswith(".httpRequest"):
            marca = "PDF ✓" if t._es_nodo_pdf(n) else "     "
            print(f"  {marca} {n['name']}: {str(n.get('parameters', {}).get('url', ''))[:110]}")


def main() -> None:
    if not (t.API and t.KEY):
        sys.exit("Faltan N8N_API_URL / N8N_API_KEY en el .env de EFE.")
    flujo = id_del_flujo()
    if "--revisar" in sys.argv:
        return revisar(flujo)
    t.log(f"Flujo de n8n: {NOMBRE_FLUJO} ({flujo})")
    pbd.ejecutar(flujo, int(t._env("SUBA_CERT_TIMEOUT_MIN") or 100),
                 webhook_url=t._env("WEBHOOK_SUBA_CERT_URL") or WEBHOOK, prefijo="WEBHOOK_SUBA_CERT",
                 origen="certificados_suba_bajo_demanda", nombre="Suba · Certificados y satisfacción")


if __name__ == "__main__":
    main()
