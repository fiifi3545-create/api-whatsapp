import pytest

from app import create_app


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Make tests independent of whatever the dev `.env` happens to set.

    Without this, `load_dotenv()` in `create_app` (or any other test that ran
    earlier) leaks values like CHATBOT_NLP_BACKEND=gemini into the process and
    breaks tests that assume the deterministic Dialogflow stub. We also
    neutralise the Agora Chat REST creds so create_app's bot-registration
    hook doesn't make real network calls during the test run.
    """
    monkeypatch.setenv("CHATBOT_NLP_BACKEND", "dialogflow")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("DIALOGFLOW_PROJECT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    # setenv("") so load_dotenv (override=False) leaves these empty.
    monkeypatch.setenv("AGORA_CHAT_APP_TOKEN", "")
    monkeypatch.setenv("AGORA_CHAT_REST_HOST", "")


@pytest.fixture
def app():
    application = create_app()
    application.config["TESTING"] = True
    application.config["WHATSAPP_VERIFY_TOKEN"] = "test-token"
    return application


@pytest.fixture
def client(app):
    return app.test_client()
