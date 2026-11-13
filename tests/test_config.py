import pytest

from app.config import ConfigurationError, Settings


def test_api_and_worker_fail_with_clear_missing_secret_errors():
    settings = Settings(_env_file=None)

    with pytest.raises(ConfigurationError, match="GITHUB_WEBHOOK_SECRET"):
        settings.require_webhook_secret()
    with pytest.raises(ConfigurationError, match="TELEGRAM_BOT_TOKEN"):
        settings.require_telegram_credentials()


def test_blank_optional_thread_id_is_treated_as_unset(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-1001234567890")
    monkeypatch.setenv("TELEGRAM_MESSAGE_THREAD_ID", "")

    settings = Settings(_env_file=None)

    assert settings.telegram_message_thread_id is None
