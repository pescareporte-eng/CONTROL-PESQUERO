#!/usr/bin/env python3
"""Autoriza Google, crea la hoja y carpetas, y guarda variables en .env.
Requiere secrets/client_secret.json de un OAuth Client ID tipo Web.
"""
from __future__ import annotations

import base64
import json
import os
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from dotenv import set_key
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parents[1]
CLIENT_FILE = ROOT / "secrets" / "client_secret.json"
ENV_FILE = ROOT / ".env"
REDIRECT_URI = "http://127.0.0.1:8765/"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/userinfo.email",
]
TABS = ["EMBARCACIONES", "INGRESO_PESCA", "VALORIZACION_PESCA", "DESPACHO_HIELO", "AUDITORIA"]
HEADERS = {
    "EMBARCACIONES": ["id", "codigo", "nombre", "matricula", "estado", "fecha_creacion"],
    "INGRESO_PESCA": ["id", "fecha", "embarcacion_id", "toneladas_tm", "kilos_kg", "observaciones", "estado", "usuario_registro", "fecha_registro"],
    "VALORIZACION_PESCA": ["id", "ingreso_pesca_id", "fecha_valorizacion", "toneladas_valorizadas", "precio_por_tm", "importe_total", "observaciones", "estado", "usuario_registro", "fecha_registro"],
    "DESPACHO_HIELO": ["id", "fecha", "embarcacion_id", "cantidad", "unidad", "precio_unitario", "importe_total", "observaciones", "estado", "usuario_registro", "fecha_registro"],
    "AUDITORIA": ["id", "fecha_hora", "usuario", "accion", "modulo", "registro_id", "detalle"],
}

class OAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        self.server.oauth_code = query.get("code", [None])[0]
        self.server.oauth_error = query.get("error", [None])[0]
        message = "Autorización recibida. Puedes cerrar esta ventana y volver a la terminal." if self.server.oauth_code else "No se recibió autorización. Vuelve a la terminal."
        body = f"<html><meta charset='utf-8'><body style='font-family:Arial;padding:40px'><h2>{message}</h2></body></html>".encode()
        self.send_response(200 if self.server.oauth_code else 400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, *args):
        return

def create_folder(drive, name, parent_id=None):
    query = f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    result = drive.files().list(q=query, spaces="drive", fields="files(id,name)", pageSize=20).execute()
    if result.get("files"):
        return result["files"][0]["id"]
    body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        body["parents"] = [parent_id]
    return drive.files().create(body=body, fields="id").execute()["id"]

def create_spreadsheet(sheets, drive, root_folder_id):
    spreadsheet = sheets.spreadsheets().create(body={
        "properties": {"title": "CONTROL_PESQUERO"},
        "sheets": [{"properties": {"title": tab}} for tab in TABS],
    }, fields="spreadsheetId,spreadsheetUrl,sheets.properties.sheetId").execute()
    sid = spreadsheet["spreadsheetId"]
    data = [{"range": f"'{tab}'!A1", "values": [HEADERS[tab]]} for tab in TABS]
    sheets.spreadsheets().values().batchUpdate(spreadsheetId=sid, body={"valueInputOption": "RAW", "data": data}).execute()
    # Mover la hoja creada a la carpeta del proyecto.
    meta = drive.files().get(fileId=sid, fields="parents").execute()
    old_parents = ",".join(meta.get("parents", []))
    drive.files().update(fileId=sid, addParents=root_folder_id, removeParents=old_parents, fields="id,parents").execute()
    return sid, spreadsheet.get("spreadsheetUrl", f"https://docs.google.com/spreadsheets/d/{sid}/edit")

def main():
    if not CLIENT_FILE.exists():
        raise SystemExit("No encuentro secrets/client_secret.json. Descarga el JSON OAuth de tipo Web y guárdalo con ese nombre.")
    client_data = json.loads(CLIENT_FILE.read_text(encoding="utf-8"))
    client = client_data.get("web") or client_data.get("installed")
    if not client:
        raise SystemExit("El JSON no tiene configuración 'web' ni 'installed'. Descarga un OAuth Client ID tipo Web.")
    if REDIRECT_URI not in client.get("redirect_uris", []):
        raise SystemExit(f"Agrega esta URI autorizada en Google Cloud > OAuth Client: {REDIRECT_URI}")

    email = input("Correo Google que será el único autorizado para el login: ").strip().lower()
    if "@" not in email:
        raise SystemExit("Correo no válido.")

    flow = Flow.from_client_secrets_file(str(CLIENT_FILE), scopes=SCOPES, redirect_uri=REDIRECT_URI)
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
    server = HTTPServer(("127.0.0.1", 8765), OAuthHandler)
    server.timeout = 300
    print("\nSe abrirá Google para autorizar el acceso a Sheets y Drive.")
    print("Si no se abre automáticamente, copia esta dirección en tu navegador:\n", auth_url, "\n")
    webbrowser.open(auth_url)
    server.handle_request()
    server.server_close()
    if getattr(server, "oauth_error", None):
        raise SystemExit(f"Google devolvió un error: {server.oauth_error}")
    if not getattr(server, "oauth_code", None):
        raise SystemExit("No se recibió el código de autorización. Reintenta el proceso.")
    flow.fetch_token(code=server.oauth_code)
    credentials = flow.credentials
    if not credentials.refresh_token:
        raise SystemExit("Google no entregó refresh token. Revoca el acceso de la aplicación en tu cuenta Google y vuelve a ejecutar el script.")

    oauth2 = build("oauth2", "v2", credentials=credentials, cache_discovery=False)
    authorized_email = (oauth2.userinfo().get().execute().get("email") or "").lower().strip()
    if authorized_email != email:
        raise SystemExit(f"La cuenta autorizada ({authorized_email}) no coincide con el correo indicado ({email}). Vuelve a ejecutar el asistente con la cuenta correcta.")

    sheets = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
    root_id = create_folder(drive, "CONTROL_PESQUERO")
    reports_id = create_folder(drive, "REPORTES", root_id)
    create_folder(drive, "RESPALDOS", root_id)
    spreadsheet_id, spreadsheet_url = create_spreadsheet(sheets, drive, root_id)

    token_b64 = base64.b64encode(credentials.to_json().encode("utf-8")).decode("ascii")
    set_key(str(ENV_FILE), "SECRET_KEY", secrets.token_urlsafe(48))
    set_key(str(ENV_FILE), "ALLOWED_EMAIL", email)
    set_key(str(ENV_FILE), "GOOGLE_CLIENT_ID", client["client_id"])
    set_key(str(ENV_FILE), "GOOGLE_CLIENT_SECRET", client["client_secret"])
    set_key(str(ENV_FILE), "GOOGLE_REDIRECT_URI", "http://127.0.0.1:5000/auth/callback")
    set_key(str(ENV_FILE), "GOOGLE_TOKEN_JSON_B64", token_b64)
    set_key(str(ENV_FILE), "GOOGLE_SPREADSHEET_ID", spreadsheet_id)
    set_key(str(ENV_FILE), "GOOGLE_DRIVE_ROOT_FOLDER_ID", root_id)
    set_key(str(ENV_FILE), "GOOGLE_DRIVE_REPORTS_FOLDER_ID", reports_id)
    set_key(str(ENV_FILE), "SESSION_COOKIE_SECURE", "false")
    set_key(str(ENV_FILE), "APP_TIMEZONE", "America/Lima")

    print("\nCONFIGURACIÓN TERMINADA")
    print(f"Hoja de cálculo: {spreadsheet_url}")
    print(f"Carpeta Drive: https://drive.google.com/drive/folders/{root_id}")
    print(f".env creado en: {ENV_FILE}")
    print("No compartas ni subas .env o client_secret.json a GitHub.")
    print("Para Render, importa las variables de .env desde Environment > Add from .env y cambia GOOGLE_REDIRECT_URI por la URL pública de Render + /auth/callback.")

if __name__ == "__main__":
    main()
