import logging

from flask import Flask
from flasgger import Swagger
from dotenv import load_dotenv

from .agora import (
    AgoraClient,
    AgoraNotConfigured,
    make_agora_client_from_env,
    make_chat_rest_client_from_env,
)
from .agora_routes import bp as agora_bp
from .agora_webhook import bp as agora_webhook_bp
from .api import bp as api_bp
from .auth import OtpStore, bp as auth_bp
from .chatbot import ChatbotEngine
from .config import Config
from .health import bp as health_bp
from .push import FcmPusher, make_pusher_from_env
from .store import Store, make_store_from_env
from .webhooks import bp as webhooks_bp


SWAGGER_TEMPLATE = {
    "swagger": "2.0",
    "info": {
        "title": "Student Chatbot Support Platform API",
        "description": (
            "REST + webhook surface backing the WhatsApp chatbot and the Flutter "
            "companion app. All `/api/*` routes (except `/api/auth/*` and "
            "`/api/config`) require `Authorization: Bearer <jwt>`. Get a token "
            "via `POST /api/auth/verify-otp`."
        ),
        "version": "1.0.0",
    },
    # `schemes` intentionally omitted — Swagger UI then uses the page's
    # protocol, so http://localhost:8080/swagger calls over HTTP and
    # https://<ngrok>/swagger calls over HTTPS (avoids mixed-content blocks).
    "securityDefinitions": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "Paste: `Bearer <jwt>`",
        }
    },
    "tags": [
        {"name": "auth", "description": "Phone-number OTP login"},
        {"name": "config", "description": "Public client configuration"},
        {"name": "users", "description": "User profile + history"},
        {"name": "groups", "description": "Study groups (create, join, members)"},
        {"name": "devices", "description": "FCM push targets"},
        {"name": "webhooks", "description": "WhatsApp + Agora Chat inbound"},
        {"name": "health", "description": "Liveness probe"},
        {"name": "agora", "description": "Agora token minting (RTC/RTM/Chat)"},
    ],
}

SWAGGER_CONFIG = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec",
            "route": "/apispec.json",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/swagger",
}


def create_app(
    config: Config | None = None,
    store: Store | None = None,
    pusher: FcmPusher | None = None,
    engine: ChatbotEngine | None = None,
    agora: AgoraClient | None = None,
) -> Flask:
    load_dotenv()
    app = Flask(__name__)
    app.config.from_object(config or Config())

    store_instance = store or make_store_from_env()
    app.extensions["store"] = store_instance
    app.extensions["otp_store"] = OtpStore()
    app.extensions["pusher"] = pusher or make_pusher_from_env(store_instance)
    # Share a single ChatbotEngine across REST + WhatsApp webhook + Agora
    # webhook so the in-process conversation-history cache is consistent
    # regardless of which entry point triggered the message.
    app.extensions["chatbot_engine"] = engine or ChatbotEngine()
    app.extensions["agora"] = agora or make_agora_client_from_env()
    # Chat REST client. Always constructed; methods raise AgoraNotConfigured
    # at call time if creds are missing, so consumers don't need to special-case
    # the dev environment.
    app.extensions["agora_chat_rest"] = make_chat_rest_client_from_env()
    # Best-effort: register the bot user in Agora Chat so we can post bot
    # replies as `bot` from the webhook. Skip silently if Chat REST isn't
    # configured or the network call fails — neither is fatal.
    try:
        chat_rest = app.extensions["agora_chat_rest"]
        if chat_rest.config.chat_is_configured and chat_rest.config.chat_app_token:
            chat_rest.ensure_user("bot")
    except (AgoraNotConfigured, Exception) as exc:
        logging.getLogger(__name__).info(
            "skipping Agora Chat bot registration: %s", exc
        )

    app.register_blueprint(health_bp)
    app.register_blueprint(webhooks_bp, url_prefix="/webhooks")
    app.register_blueprint(agora_webhook_bp, url_prefix="/webhooks")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(agora_bp, url_prefix="/api/agora")

    Swagger(app, template=SWAGGER_TEMPLATE, config=SWAGGER_CONFIG)

    return app
