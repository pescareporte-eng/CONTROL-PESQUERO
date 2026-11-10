from flask import Blueprint, render_template, session, redirect, url_for

pages_bp = Blueprint("pages", __name__)

def page_context():
    return {
        "user_email": session.get("user_email", ""),
        "user_name": session.get("user_name", ""),
        "user_picture": session.get("user_picture", ""),
    }

@pages_bp.get("/")
def index():
    if not session.get("user_email"):
        return redirect(url_for("auth.login"))
    return redirect(url_for("pages.dashboard"))

@pages_bp.get("/dashboard")
def dashboard():
    if not session.get("user_email"): return redirect(url_for("auth.login"))
    return render_template("dashboard.html", **page_context(), active_page="dashboard", page_title="Dashboard")

@pages_bp.get("/embarcaciones")
def vessels():
    if not session.get("user_email"): return redirect(url_for("auth.login"))
    return render_template("vessels.html", **page_context(), active_page="vessels", page_title="Embarcaciones")

@pages_bp.get("/pesca")
def fishing():
    if not session.get("user_email"): return redirect(url_for("auth.login"))
    return render_template("fishing.html", **page_context(), active_page="fishing", page_title="Ingreso de pesca")

@pages_bp.get("/valorizacion")
def valuation():
    if not session.get("user_email"): return redirect(url_for("auth.login"))
    return render_template("valuation.html", **page_context(), active_page="valuation", page_title="Valorización de pesca")

@pages_bp.get("/hielo")
def ice():
    if not session.get("user_email"): return redirect(url_for("auth.login"))
    return render_template("ice.html", **page_context(), active_page="ice", page_title="Despacho de hielo")

@pages_bp.get("/gastos-estadia")
def stay_expenses():
    if not session.get("user_email"): return redirect(url_for("auth.login"))
    return render_template("stay_expenses.html", **page_context(), active_page="stay_expenses", page_title="Gastos de estadía")

@pages_bp.get("/reportes")
def reports():
    if not session.get("user_email"): return redirect(url_for("auth.login"))
    return render_template("reports.html", **page_context(), active_page="reports", page_title="Reportes")
