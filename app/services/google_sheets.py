"""Repositorio de CONTROL-PESQUERO mediante Google Apps Script.

Google Apps Script se ejecuta bajo la cuenta propietaria y realiza las
operaciones en la hoja y las carpetas existentes de Google Drive. El servidor
Flask solo conserva la URL de la Web App y un secreto compartido.
"""
from __future__ import annotations

import base64
import threading
from datetime import datetime
from typing import Any

import requests
from flask import current_app

HEADERS: dict[str, list[str]] = {
    "EMBARCACIONES": ["id", "codigo", "nombre", "matricula", "estado", "fecha_creacion"],
    "INGRESO_PESCA": ["id", "fecha", "embarcacion_id", "toneladas_tm", "kilos_kg", "observaciones", "estado", "usuario_registro", "fecha_registro"],
    "VALORIZACION_PESCA": ["id", "ingreso_pesca_id", "fecha_valorizacion", "toneladas_valorizadas", "precio_por_tm", "importe_total", "observaciones", "estado", "usuario_registro", "fecha_registro", "kilos_valorizados", "precio_por_kg", "importe_tm", "importe_kg", "tipo_valorizacion"],
    "DESPACHO_HIELO": ["id", "fecha", "embarcacion_id", "cantidad", "unidad", "precio_unitario", "importe_total", "observaciones", "estado", "usuario_registro", "fecha_registro"],
    "GASTOS_ESTADIA": ["id", "fecha", "descripcion", "precio", "estado", "usuario_registro", "fecha_registro"],
    "AUDITORIA": ["id", "fecha_hora", "usuario", "accion", "modulo", "registro_id", "detalle"],
}


class GoogleSheetsRepository:
    """Mantiene la misma interfaz usada por las rutas, delegando a Apps Script."""

    _lock = threading.RLock()

    def __init__(
        self,
        apps_script_url: str,
        apps_script_secret: str,
        spreadsheet_id: str,
        root_folder_id: str,
        reports_folder_id: str,
    ):
        if not all([apps_script_url, apps_script_secret, spreadsheet_id, reports_folder_id]):
            raise RuntimeError(
                "Falta configurar Google: URL/secreto de Apps Script, hoja o carpeta de reportes."
            )
        self.apps_script_url = apps_script_url.strip()
        self.apps_script_secret = apps_script_secret.strip()
        self.spreadsheet_id = spreadsheet_id.strip()
        self.root_folder_id = (root_folder_id or "").strip()
        self.reports_folder_id = reports_folder_id.strip()
        self.http = requests.Session()

        # Comprueba únicamente la conectividad. No crea pestañas ni modifica
        # encabezados al iniciar el servicio: el esquema existente se conserva.
        self._call("ping")

    def _call(self, action: str, **params: Any) -> Any:
        payload = {"secret": self.apps_script_secret, "action": action, **params}
        try:
            response = self.http.post(
                self.apps_script_url,
                json=payload,
                timeout=(10, 110),
                allow_redirects=True,
            )
            response.raise_for_status()
            try:
                result = response.json()
            except ValueError as exc:
                preview = (response.text or "")[:240].replace("\n", " ")
                raise RuntimeError(
                    f"Apps Script no devolvió JSON válido (HTTP {response.status_code}): {preview}"
                ) from exc
        except requests.RequestException as exc:
            current_app.logger.exception("Fallo al conectar con Google Apps Script (%s)", action)
            raise RuntimeError(
                "No se pudo conectar con el servicio de Google. Revisa la URL de Apps Script y su despliegue."
            ) from exc

        if not isinstance(result, dict) or result.get("ok") is not True:
            message = result.get("error", "Respuesta no válida del servicio de Google.") if isinstance(result, dict) else "Respuesta no válida del servicio de Google."
            current_app.logger.error("Google Apps Script rechazó la operación %s: %s", action, message)
            raise RuntimeError(str(message))
        return result.get("data")

    def get_all(self, tab: str) -> list[dict[str, str]]:
        if tab not in HEADERS:
            raise ValueError("Pestaña no permitida")
        with self._lock:
            data = self._call("get_all", tab=tab)
        if not isinstance(data, list):
            raise RuntimeError(f"Google devolvió datos no válidos para la pestaña {tab}.")
        return data

    def append(self, tab: str, item: dict[str, Any]) -> None:
        if tab not in HEADERS:
            raise ValueError("Pestaña no permitida")
        with self._lock:
            self._call("append", tab=tab, item=item)

    def find(self, tab: str, record_id: str) -> tuple[int, dict[str, str]] | None:
        rows = self.get_all(tab)
        for index, row in enumerate(rows, start=2):
            if row.get("id") == record_id:
                return index, row
        return None

    def update(self, tab: str, record_id: str, changes: dict[str, Any]) -> dict[str, str] | None:
        if tab not in HEADERS:
            raise ValueError("Pestaña no permitida")
        found = self.find(tab, record_id)
        if not found:
            return None
        row_number, old = found
        with self._lock:
            updated = self._call(
                "update_row",
                tab=tab,
                row_number=row_number,
                changes={key: str(value) for key, value in changes.items()},
            )
        return updated if isinstance(updated, dict) else None

    def audit(self, user: str, action: str, module: str, record_id: str, detail: str = "") -> None:
        self.append("AUDITORIA", {
            "id": __import__("uuid").uuid4().hex,
            "fecha_hora": datetime.now().isoformat(timespec="seconds"),
            "usuario": user,
            "accion": action,
            "modulo": module,
            "registro_id": record_id,
            "detalle": detail,
        })

    def upload_report(
        self,
        filename: str,
        content: bytes,
        mime_type: str,
        year: str,
        category: str,
    ) -> dict[str, str]:
        result = self._call(
            "upload_report",
            filename=filename,
            mime_type=mime_type,
            year=str(year),
            category=category,
            content_base64=base64.b64encode(content).decode("ascii"),
        )
        if not isinstance(result, dict) or not result.get("id"):
            raise RuntimeError("Google no confirmó que el reporte se haya guardado en Drive.")
        return {
            "id": str(result.get("id", "")),
            "name": str(result.get("name", filename)),
            "url": str(result.get("url", "")),
        }


_repository_instance = None
_repository_init_lock = threading.Lock()


def get_repository() -> GoogleSheetsRepository:
    # Un solo cliente por proceso, igual que la implementación anterior.
    global _repository_instance
    if _repository_instance is None:
        with _repository_init_lock:
            if _repository_instance is None:
                cfg = current_app.config
                _repository_instance = GoogleSheetsRepository(
                    cfg["GOOGLE_APPS_SCRIPT_URL"],
                    cfg["GOOGLE_APPS_SCRIPT_SECRET"],
                    cfg["GOOGLE_SPREADSHEET_ID"],
                    cfg.get("GOOGLE_DRIVE_ROOT_FOLDER_ID", ""),
                    cfg["GOOGLE_DRIVE_REPORTS_FOLDER_ID"],
                )
    return _repository_instance
