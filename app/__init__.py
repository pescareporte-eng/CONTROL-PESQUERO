import os
from flask import Flask, jsonify, request
from flask_wtf.csrf import CSRFProtect, CSRFError
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv

csrf = CSRFProtect()
oauth = OAuth()

def create_app():
    load_dotenv()
    app = Flask(__name__)
    app.config.from_object("config.Config")
    csrf.init_app(app)
    oauth.init_app(app)

    if app.config["GOOGLE_CLIENT_ID"] and app.config["GOOGLE_CLIENT_SECRET"]:
        oauth.register(
            name="google",
            client_id=app.config["GOOGLE_CLIENT_ID"],
            client_secret=app.config["GOOGLE_CLIENT_SECRET"],
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )

    from .routes.auth import auth_bp
    from .routes.pages import pages_bp
    from .routes.api import api_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "La sesión del formulario venció. Recarga la página e inténtalo nuevamente."}), 400
        return "La sesión venció. Vuelve a cargar la página.", 400

    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Recurso no encontrado."}), 404
        return "Página no encontrada", 404

    @app.errorhandler(500)
    def server_error(error):
        app.logger.exception("Error interno: %s", error)
        if request.path.startswith("/api/"):
            return jsonify({"error": "Ocurrió un error interno. Revisa la configuración y los registros del servidor."}), 500
        return "Ocurrió un error interno.", 500

    return app
