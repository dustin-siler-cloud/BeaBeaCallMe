import logging
import time
from flask import Flask, jsonify
from config import Config
from app.utils.security_headers import add_security_headers

START_TIME = time.time()


def create_app():
    app = Flask(__name__)
    app.secret_key = Config.SECRET_KEY

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    from app.routes.ivr import ivr_bp
    from app.routes.voicemail import voicemail_bp

    app.register_blueprint(ivr_bp)
    app.register_blueprint(voicemail_bp)
    app.after_request(add_security_headers)

    @app.get("/health")
    def health():
        uptime_seconds = int(time.time() - START_TIME)
        return jsonify({"status": "ok", "uptime_seconds": uptime_seconds})

    return app