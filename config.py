import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "cambia-esta-clave-en-produccion")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    WTF_CSRF_TIME_LIMIT = None

    ALLOWED_EMAIL = os.getenv("ALLOWED_EMAIL", "").strip().lower()
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://127.0.0.1:5000/auth/callback")

    GOOGLE_TOKEN_JSON_B64 = os.getenv("GOOGLE_TOKEN_JSON_B64", "")
    GOOGLE_SPREADSHEET_ID = os.getenv("GOOGLE_SPREADSHEET_ID", "")
    GOOGLE_DRIVE_ROOT_FOLDER_ID = os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID", "")
    GOOGLE_DRIVE_REPORTS_FOLDER_ID = os.getenv("GOOGLE_DRIVE_REPORTS_FOLDER_ID", "")

    APP_TIMEZONE = os.getenv("APP_TIMEZONE", "America/Lima")
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024
