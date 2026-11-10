from functools import wraps
from flask import Blueprint, current_app, redirect, url_for, session, request, flash, render_template
from .. import oauth

auth_bp = Blueprint("auth", __name__)

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_email"):
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped

@auth_bp.get("/login")
def login():
    if session.get("user_email"):
        return redirect(url_for("pages.dashboard"))
    return render_template("login.html")

@auth_bp.get("/auth/google")
def google_login():
    if not current_app.config["GOOGLE_CLIENT_ID"] or not current_app.config["GOOGLE_CLIENT_SECRET"]:
        flash("Falta configurar las credenciales OAuth de Google.", "danger")
        return redirect(url_for("auth.login"))
    redirect_uri = current_app.config["GOOGLE_REDIRECT_URI"]
    return oauth.google.authorize_redirect(redirect_uri, prompt="select_account")

@auth_bp.get("/auth/callback")
def google_callback():
    try:
        token = oauth.google.authorize_access_token()
        userinfo = token.get("userinfo") or oauth.google.userinfo().json()
    except Exception as exc:
        current_app.logger.exception("OAuth Google falló: %s", exc)
        flash("No se pudo completar el acceso con Google.", "danger")
        return redirect(url_for("auth.login"))

    email = (userinfo.get("email") or "").lower().strip()
    allowed = current_app.config["ALLOWED_EMAIL"]
    if not email or userinfo.get("email_verified") is False:
        flash("Google no pudo verificar la dirección de correo.", "danger")
        return redirect(url_for("auth.login"))
    if not allowed or email != allowed:
        session.clear()
        flash("Esta cuenta de Google no está autorizada para ingresar.", "danger")
        return redirect(url_for("auth.login"))

    session.clear()
    session.permanent = True
    session["user_email"] = email
    session["user_name"] = userinfo.get("name") or email
    session["user_picture"] = userinfo.get("picture", "")
    return redirect(url_for("pages.dashboard"))

@auth_bp.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
