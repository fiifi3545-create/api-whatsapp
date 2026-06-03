import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret")

    WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
    WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
    WHATSAPP_API_BASE = os.environ.get(
        "WHATSAPP_API_BASE", "https://graph.facebook.com/v20.0"
    )
    META_APP_SECRET = os.environ.get("META_APP_SECRET", "")

    DIALOGFLOW_PROJECT_ID = os.environ.get("DIALOGFLOW_PROJECT_ID", "")
    DIALOGFLOW_LANGUAGE_CODE = os.environ.get("DIALOGFLOW_LANGUAGE_CODE", "en")

    # NLP backend: "dialogflow" (default) or "gemma" (LLM via Ollama).
    # Either way, faqs.json remains the source of answer text — the NLP layer
    # only classifies the intent. Pattern A from the design notes.
    CHATBOT_NLP_BACKEND = os.environ.get("CHATBOT_NLP_BACKEND", "dialogflow").strip().lower()
    OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:4b")

    FIRESTORE_PROJECT_ID = os.environ.get("FIRESTORE_PROJECT_ID", "")

    CHATBOT_FALLBACK_CONTACT = os.environ.get(
        "CHATBOT_FALLBACK_CONTACT",
        "Please contact the Student Affairs office for help with this question.",
    )
    CHATBOT_CONFIDENCE_THRESHOLD = float(
        os.environ.get("CHATBOT_CONFIDENCE_THRESHOLD", "0.6")
    )

    JWT_SECRET = os.environ.get("JWT_SECRET", "dev-jwt-secret-change-me")
    JWT_TTL_DAYS = int(os.environ.get("JWT_TTL_DAYS", "30"))
    OTP_ECHO_IN_RESPONSE = os.environ.get("OTP_ECHO_IN_RESPONSE", "true").lower() == "true"

    # How the OTP is delivered: "sms" (Hubtel), "whatsapp" (Meta template), or
    # "both". WhatsApp needs an approved Authentication template
    # (WHATSAPP_OTP_TEMPLATE) plus the WABA credentials below.
    OTP_DELIVERY_CHANNEL = os.environ.get("OTP_DELIVERY_CHANNEL", "sms").strip().lower()

    FCM_PROJECT_ID = os.environ.get("FCM_PROJECT_ID", "")

    WHATSAPP_BOT_NUMBER = os.environ.get("WHATSAPP_BOT_NUMBER", "")

    # Mention token the bot listens for inside WhatsApp groups. Group messages
    # that don't contain this token are ignored — required by WhatsApp group
    # etiquette (the bot must not respond to every message in the group).
    BOT_MENTION_NAME = os.environ.get("BOT_MENTION_NAME", "@bot")

    # Meta-approved Authentication template name. Created in Meta Business
    # Manager → WhatsApp Manager → Message templates (category: Authentication).
    # Default placeholder — set the real name once approved.
    WHATSAPP_OTP_TEMPLATE = os.environ.get("WHATSAPP_OTP_TEMPLATE", "otp_code")
    WHATSAPP_OTP_LANGUAGE = os.environ.get("WHATSAPP_OTP_LANGUAGE", "en")

    # Hubtel SMS — used to deliver OTPs to Ghanaian numbers.
    # Get credentials at https://unity.hubtel.com → API Keys.
    HUBTEL_CLIENT_ID = os.environ.get("HUBTEL_CLIENT_ID", "")
    HUBTEL_CLIENT_SECRET = os.environ.get("HUBTEL_CLIENT_SECRET", "")
    HUBTEL_SENDER_ID = os.environ.get("HUBTEL_SENDER_ID", "")
