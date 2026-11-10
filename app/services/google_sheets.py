"""Repositorio Google Sheets + Drive. Google Sheets es el almacenamiento principal."""
from __future__ import annotations

import base64
import io
import json
import threading
from datetime import datetime
from typing import Any

from flask import current_app
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/userinfo.email",
]

HEADERS: dict[str, list[str]] = {
    "EMBARCACIONES": ["id", "codigo", "nombre", "matricula", "estado", "fecha_creacion"],
    "INGRESO_PESCA": ["id", "fecha", "embarcacion_id", "toneladas_tm", "kilos_kg", "observaciones", "estado", "usuario_registro", "fecha_registro"],
    "VALORIZACION_PESCA": ["id", "ingreso_pesca_id", "fecha_valorizacion", "toneladas_valorizadas", "precio_por_tm", "importe_total", "observaciones", "estado", "usuario_registro", "fecha_registro", "kilos_valorizados", "precio_por_kg", "importe_tm", "importe_kg", "tipo_valorizacion"],
    "DESPACHO_HIELO": ["id", "fecha", "embarcacion_id", "cantidad", "unidad", "precio_unitario", "importe_total", "observaciones", "estado", "usuario_registro", "fecha_registro"],
    "GASTOS_ESTADIA": ["id", "fecha", "descripcion", "precio", "estado", "usuario_registro", "fecha_registro"],
    "AUDITORIA": ["id", "fecha_hora", "usuario", "accion", "modulo", "registro_id", "detalle"],
}

class GoogleSheetsRepository:
    _lock = threading.RLock()

    def __init__(self, token_json_b64: str, spreadsheet_id: str, root_folder_id: str, reports_folder_id: str):
        if not all([token_json_b64, spreadsheet_id, root_folder_id, reports_folder_id]):
            raise RuntimeError("Falta configurar Google: token, hoja de cálculo o carpetas de Drive.")
        token_info = json.loads(base64.b64decode(token_json_b64).decode("utf-8"))
        self.credentials = Credentials.from_authorized_user_info(token_info, scopes=SCOPES)
        if self.credentials.expired and self.credentials.refresh_token:
            self.credentials.refresh(Request())
        if not self.credentials.valid:
            raise RuntimeError("La autorización de Google no es válida. Repite scripts/setup_google.py.")
        self.sheets = build("sheets", "v4", credentials=self.credentials, cache_discovery=False)
        self.drive = build("drive", "v3", credentials=self.credentials, cache_discovery=False)
        self.spreadsheet_id = spreadsheet_id
        self.root_folder_id = root_folder_id
        self.reports_folder_id = reports_folder_id
        # Amplía pestañas existentes con columnas nuevas sin mover ni borrar históricos.
        self._ensure_schema_headers()

    @staticmethod
    def _column_name(number: int) -> str:
        result = ""
        while number:
            number, remainder = divmod(number - 1, 26)
            result = chr(65 + remainder) + result
        return result

    def _read_headers(self, tab: str) -> list[str]:
        result = self.sheets.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=self._range(tab, "1:1"),
            valueRenderOption="FORMATTED_VALUE",
        ).execute()
        values = result.get("values", [])
        return [str(value) for value in values[0]] if values else []

    def _ensure_schema_headers(self) -> None:
        # Primero verifica qué pestañas existen. Google Sheets no permite leer
        # un rango de una pestaña que todavía no fue creada (por ejemplo,
        # GASTOS_ESTADIA en instalaciones anteriores).
        spreadsheet = self.sheets.spreadsheets().get(
            spreadsheetId=self.spreadsheet_id,
            fields="sheets.properties.title",
        ).execute()
        existing_tabs = {
            sheet.get("properties", {}).get("title", "")
            for sheet in spreadsheet.get("sheets", [])
        }
        missing_tabs = [tab for tab in HEADERS if tab not in existing_tabs]
        if missing_tabs:
            self.sheets.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={
                    "requests": [
                        {"addSheet": {"properties": {"title": tab}}}
                        for tab in missing_tabs
                    ]
                },
            ).execute()

        # Completa encabezados faltantes al final de cada fila, sin borrar ni
        # reordenar columnas o registros que ya existían.
        for tab, required in HEADERS.items():
            existing = self._read_headers(tab)
            if not existing:
                self.sheets.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=self._range(tab, "A1"),
                    valueInputOption="RAW",
                    body={"values": [required]},
                ).execute()
                continue
            missing = [name for name in required if name not in existing]
            if missing:
                first_col = self._column_name(len(existing) + 1)
                last_col = self._column_name(len(existing) + len(missing))
                self.sheets.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=self._range(tab, f"{first_col}1:{last_col}1"),
                    valueInputOption="RAW",
                    body={"values": [missing]},
                ).execute()

    def _range(self, tab: str, suffix: str = "A:Z") -> str:
        if tab not in HEADERS:
            raise ValueError("Pestaña no permitida")
        return f"'{tab}'!{suffix}"

    def get_all(self, tab: str) -> list[dict[str, str]]:
        with self._lock:
            result = self.sheets.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=self._range(tab),
                valueRenderOption="FORMATTED_VALUE",
            ).execute()
        values = result.get("values", [])
        if not values:
            return []
        headers = values[0]
        rows = []
        for raw in values[1:]:
            padded = raw + [""] * (len(headers) - len(raw))
            rows.append({headers[i]: str(padded[i]) for i in range(len(headers))})
        return rows

    def append(self, tab: str, item: dict[str, Any]) -> None:
        headers = self._read_headers(tab) or HEADERS[tab]
        row = [str(item.get(key, "")) for key in headers]
        with self._lock:
            self.sheets.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=self._range(tab),
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": [row]},
            ).execute()

    def find(self, tab: str, record_id: str) -> tuple[int, dict[str, str]] | None:
        rows = self.get_all(tab)
        for index, row in enumerate(rows, start=2):
            if row.get("id") == record_id:
                return index, row
        return None

    def update(self, tab: str, record_id: str, changes: dict[str, Any]) -> dict[str, str] | None:
        found = self.find(tab, record_id)
        if not found:
            return None
        row_number, old = found
        headers = self._read_headers(tab) or HEADERS[tab]
        old.update({k: str(v) for k, v in changes.items() if k in headers})
        row = [old.get(key, "") for key in headers]
        last_col = self._column_name(len(row))
        with self._lock:
            self.sheets.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=self._range(tab, f"A{row_number}:{last_col}{row_number}"),
                valueInputOption="RAW",
                body={"values": [row]},
            ).execute()
        return old

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

    def _find_or_create_folder(self, name: str, parent_id: str) -> str:
        safe_name = name.replace("'", "\\'")
        query = (
            f"name = '{safe_name}' and mimeType = 'application/vnd.google-apps.folder' "
            f"and '{parent_id}' in parents and trashed = false"
        )
        result = self.drive.files().list(q=query, spaces="drive", fields="files(id,name)", pageSize=20).execute()
        files = result.get("files", [])
        if files:
            return files[0]["id"]
        created = self.drive.files().create(
            body={"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]},
            fields="id",
        ).execute()
        return created["id"]

    def upload_report(self, filename: str, content: bytes, mime_type: str, year: str, category: str) -> dict[str, str]:
        year_id = self._find_or_create_folder(str(year), self.reports_folder_id)
        category_id = self._find_or_create_folder(category, year_id)
        media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime_type, resumable=False)
        result = self.drive.files().create(
            body={"name": filename, "parents": [category_id]},
            media_body=media,
            fields="id,name,webViewLink",
        ).execute()
        return {"id": result.get("id", ""), "name": result.get("name", filename), "url": result.get("webViewLink", "")}


_repository_instance = None
_repository_init_lock = threading.Lock()

def get_repository() -> GoogleSheetsRepository:
    # Un solo repositorio por proceso: conserva el access token renovado en memoria.
    global _repository_instance
    if _repository_instance is None:
        with _repository_init_lock:
            if _repository_instance is None:
                cfg = current_app.config
                _repository_instance = GoogleSheetsRepository(
                    cfg["GOOGLE_TOKEN_JSON_B64"],
                    cfg["GOOGLE_SPREADSHEET_ID"],
                    cfg["GOOGLE_DRIVE_ROOT_FOLDER_ID"],
                    cfg["GOOGLE_DRIVE_REPORTS_FOLDER_ID"],
                )
    return _repository_instance
