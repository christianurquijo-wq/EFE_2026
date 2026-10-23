"""
ops_sync_n8n.py -- Copia las ejecuciones de n8n a LOG_EJECUCIONES (oct-2026).

Reemplaza el flujo "OPS - Sync ejecuciones n8n": corre en GitHub Actions
(.github/workflows/ops_sync_n8n.yml, cada hora), así el historial no depende de
que n8n esté arriba para sincronizarse a sí mismo.

Qué hace:
  1. Lee las ejecuciones recientes de n8n por su API pública.
  2. Agrega a LOG_EJECUCIONES las terminadas que aún no estén (id_ejecucion = n8n-<id>),
     con el mismo formato que usaba el flujo de n8n. En las fallidas guarda el nodo
     y el mensaje de error.
  3. Si alguna falló en la última ventana, manda UN correo de alerta (Gmail, vía ops_logger).

Configuración (entorno o .env de la raíz; el .env viaja en SECRETS_BUNDLE):
    N8N_API_URL   https://n8n.kuepa.com/api/v1
    N8N_API_KEY   API key de n8n (Settings -> n8n API)
    N8N_IGNORAR   IDs de flujos a ignorar, separados por coma (opcional)
    OPS_SHEET_ID / OPS_LOG_SA_JSON   los mismos secrets que usa ops_logger
No es un ETL: está excluido del lote nocturno en trigger.py.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

import ops_logger as ops

LOOKBACK_DIAS = 3          # hasta dónde mirar hacia atrás en cada corrida
VENTANA_ALERTA_MIN = 90    # solo alerta fallos recientes (el cron corre cada hora)
IGNORAR_BASE = {"cFI8A5J6S5Fyqv7K", "JKlWiKnMFOimNnpE"}  # flujos OPS - Sync y OPS - Alertas
FINALES = {"success", "error", "crashed", "canceled"}
MODO = {"webhook": "boton", "trigger": "cron", "manual": "manual_n8n", "retry": "manual_n8n",
        "integrated": "manual_n8n", "cli": "manual_n8n", "error": "n8n_error"}


def _cfg(clave: str) -> str:
    """Del entorno o del .env de la raíz (solo la clave pedida)."""
    valor = os.getenv(clave, "").strip()
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if valor or not os.path.exists(ruta):
        return valor
    with open(ruta, encoding="utf-8-sig") as f:
        for linea in f:
            if "=" in linea and not linea.lstrip().startswith("#"):
                k, v = linea.split("=", 1)
                if k.strip() == clave:
                    return v.split(" #")[0].strip().strip('"').strip("'")
    return ""


API = _cfg("N8N_API_URL").rstrip("/")
KEY = _cfg("N8N_API_KEY")
IGNORAR = IGNORAR_BASE | {x.strip() for x in _cfg("N8N_IGNORAR").split(",") if x.strip()}
RAIZ_N8N = API.split("/api/")[0]
_nombres: dict[str, str] = {}


class N8nNoDisponible(Exception):
    """n8n respondió 5xx o no contestó: el servidor está caído o saturado."""


def _get(ruta: str, **params) -> dict:
    """GET a la API con 3 reintentos (5, 15, 30 s) si n8n responde 5xx o no contesta."""
    for espera in (5, 15, 30, None):
        try:
            r = requests.get(f"{API}{ruta}", params=params, timeout=30,
                             headers={"X-N8N-API-KEY": KEY, "Accept": "application/json"})
            if r.status_code < 500:
                r.raise_for_status()  # 4xx (key, URL): error real, sin reintento
                return r.json()
            motivo = f"HTTP {r.status_code}"
        except (requests.ConnectionError, requests.Timeout) as exc:
            motivo = type(exc).__name__
        if espera is None:
            raise N8nNoDisponible(motivo)
        print(f"[sync n8n] n8n no responde ({motivo}); reintento en {espera} s")
        time.sleep(espera)


def _dt(valor) -> datetime | None:
    return datetime.fromisoformat(str(valor).replace("Z", "+00:00")) if valor else None


def _bogota(valor) -> str:
    d = _dt(valor)
    return d.astimezone(ops.TZ_BOGOTA).isoformat(timespec="seconds") if d else ""


def nombre_flujo(wid: str) -> str:
    if wid not in _nombres:
        try:
            _nombres[wid] = _get(f"/workflows/{wid}").get("name") or wid
        except (requests.RequestException, N8nNoDisponible):
            _nombres[wid] = wid
    return _nombres[wid]


def ejecuciones_recientes() -> list[dict]:
    limite = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DIAS)
    salida, cursor = [], None
    for _ in range(40):  # máx. 2.000 ejecuciones por corrida
        params = {"limit": 50, **({"cursor": cursor} if cursor else {})}
        pagina = _get("/executions", **params)
        datos = pagina.get("data", [])
        salida += datos
        cursor = pagina.get("nextCursor")
        if not cursor or not datos or all((_dt(e.get("startedAt")) or limite) < limite for e in datos):
            break
    return [e for e in salida if (_dt(e.get("startedAt")) or limite) >= limite]


def ids_registrados() -> set[str]:
    sheet_id = os.getenv("OPS_SHEET_ID", "").strip()
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{ops.HOJA_LOG}!A:A"
    r = ops._sesion_sheets().get(url, timeout=30)
    r.raise_for_status()
    return {fila[0] for fila in r.json().get("values", []) if fila}


def error_de(ejecucion_id: str, estado: str) -> str:
    try:
        res = (_get(f"/executions/{ejecucion_id}", includeData="true").get("data") or {}).get("resultData") or {}
    except (requests.RequestException, N8nNoDisponible):
        return f"n8n status: {estado}"
    err = res.get("error") or {}
    nodo = err.get("node", {}).get("name") if isinstance(err.get("node"), dict) else err.get("node")
    nodo = nodo or res.get("lastNodeExecuted") or ""
    msg = err.get("message") or err.get("description") or f"n8n status: {estado}"
    return (f"Nodo «{nodo}»: " if nodo else "") + str(msg)[:1200]


def fila(e: dict) -> dict:
    wid, eid, estado = str(e.get("workflowId")), str(e.get("id")), str(e.get("status"))
    inicio, fin = _dt(e.get("startedAt")), _dt(e.get("stoppedAt"))
    return {
        "id_ejecucion": f"n8n-{eid}", "request_id": "",
        "fecha_inicio": _bogota(e.get("startedAt")), "fecha_fin": _bogota(e.get("stoppedAt")),
        "duracion_seg": round((fin - inicio).total_seconds(), 1) if inicio and fin else "",
        "plataforma": "n8n", "repo": "n8n", "automatizacion_id": f"n8n:{wid}", "script": wid,
        "origen": MODO.get(str(e.get("mode")), str(e.get("mode"))),
        "disparado_por": "panel" if e.get("mode") == "webhook" else "n8n",
        "estado": "EXITOSO" if estado == "success" else "FALLIDO",
        "codigo_salida": 0 if estado == "success" else 1,
        "error": "" if estado == "success" else error_de(eid, estado),
        "run_url": f"{RAIZ_N8N}/workflow/{wid}/executions/{eid}", "lote": "",
    }


def anexar(filas: list[dict]) -> None:
    sheet_id = os.getenv("OPS_SHEET_ID", "").strip()
    url = (f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/"
           f"{ops.HOJA_LOG}!A1:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS")
    valores = [["" if f.get(c) is None else f.get(c) for c in ops.COLUMNAS] for f in filas]
    r = ops._sesion_sheets().post(url, json={"values": valores}, timeout=60)
    r.raise_for_status()


def alertar(fallidas: list[tuple[dict, dict]]) -> None:
    ahora = datetime.now(timezone.utc)
    recientes = [(e, f) for e, f in fallidas
                 if (_dt(e.get("stoppedAt")) or ahora) >= ahora - timedelta(minutes=VENTANA_ALERTA_MIN)]
    if not recientes:
        return
    lineas = [f"Fallaron {len(recientes)} ejecución(es) de n8n en la última hora y media:", ""]
    for e, f in recientes:
        lineas += [f"■ {nombre_flujo(f['script'])} — {f['fecha_inicio']} ({f['origen']})",
                   f"  {f['error']}", f"  {f['run_url']}", ""]
    lineas += ["—", "Historial: Dashboard → Operaciones → Análisis de ejecuciones."]
    ops._enviar_correo(f"[OPS] n8n: {len(recientes)} flujo(s) fallaron", "\n".join(lineas))


def main() -> None:
    if not (API and KEY):
        sys.exit("Faltan N8N_API_URL / N8N_API_KEY (en el .env o como variables de entorno).")
    registrados = ids_registrados()
    try:
        recientes = ejecuciones_recientes()
    except N8nNoDisponible as exc:
        # n8n caído no es un fallo del sync: la próxima corrida recupera lo pendiente
        # (mira 3 días hacia atrás). Queda como aviso amarillo en GitHub, no en rojo.
        print(f"::warning::n8n no disponible ({exc}). Se reintenta en la próxima corrida.")
        return
    nuevas = [e for e in recientes
              if str(e.get("status")) in FINALES and e.get("stoppedAt")
              and str(e.get("workflowId")) not in IGNORAR
              and f"n8n-{e.get('id')}" not in registrados]
    nuevas.sort(key=lambda e: str(e.get("startedAt")))
    filas = [fila(e) for e in nuevas]
    if filas:
        anexar(filas)
    fallidas = [(e, f) for e, f in zip(nuevas, filas) if f["estado"] != "EXITOSO"]
    print(f"[sync n8n] {len(filas)} ejecuciones nuevas registradas · {len(fallidas)} fallidas")
    alertar(fallidas)


if __name__ == "__main__":
    main()
