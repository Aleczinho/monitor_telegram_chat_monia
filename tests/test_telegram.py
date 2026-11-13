import json

import httpx
import pytest

from app.telegram import TelegramClient, TelegramError


@pytest.mark.asyncio
async def test_send_message_uses_html_chat_and_optional_thread(settings):
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    settings.telegram_message_thread_id = 17
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        telegram = TelegramClient(settings, client)
        await telegram.send_message("<b>test</b>")

    assert captured["path"].endswith("/sendMessage")
    assert captured["payload"]["chat_id"] == settings.telegram_chat_id
    assert captured["payload"]["text"] == "<b>test</b>"
    assert captured["payload"]["parse_mode"] == "HTML"
    assert captured["payload"]["message_thread_id"] == 17


@pytest.mark.asyncio
async def test_rate_limit_retry_after_is_reported(settings):
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={
                "ok": False,
                "error_code": 429,
                "parameters": {"retry_after": 25},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        telegram = TelegramClient(settings, client)
        with pytest.raises(TelegramError) as raised:
            await telegram.send_message("test")

    assert raised.value.retryable
    assert raised.value.retry_after == 25
    assert raised.value.code == "telegram_rate_limited"


@pytest.mark.asyncio
async def test_client_error_is_not_retried(settings):
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"ok": False, "error_code": 400})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        telegram = TelegramClient(settings, client)
        with pytest.raises(TelegramError) as raised:
            await telegram.send_message("test")

    assert not raised.value.retryable
    assert raised.value.code == "telegram_http_400"


@pytest.mark.asyncio
async def test_invalid_api_response_is_retryable(settings):
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        telegram = TelegramClient(settings, client)
        with pytest.raises(TelegramError) as raised:
            await telegram.send_message("test")

    assert raised.value.retryable
    assert raised.value.code == "telegram_invalid_response"


@pytest.mark.asyncio
async def test_server_error_is_retryable(settings):
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"ok": False})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        telegram = TelegramClient(settings, client)
        with pytest.raises(TelegramError) as raised:
            await telegram.send_message("test")

    assert raised.value.retryable
    assert raised.value.code == "telegram_server_error"


@pytest.mark.asyncio
async def test_network_error_is_retryable(settings):
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network unavailable", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        telegram = TelegramClient(settings, client)
        with pytest.raises(TelegramError) as raised:
            await telegram.send_message("test")

    assert raised.value.retryable
    assert raised.value.code == "telegram_network_error"
