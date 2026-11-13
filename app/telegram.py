import httpx

from app.config import Settings


class TelegramError(Exception):
    def __init__(
        self,
        code: str,
        *,
        retryable: bool,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.retry_after = retry_after


class TelegramClient:
    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._token, self._chat_id = settings.require_telegram_credentials()
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        self._owns_client = client is None

    async def send_message(self, message_html: str) -> None:
        token = self._token.get_secret_value()
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload: dict[str, object] = {
            "chat_id": self._chat_id,
            "text": message_html,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if self._settings.telegram_message_thread_id is not None:
            payload["message_thread_id"] = self._settings.telegram_message_thread_id

        try:
            response = await self._client.post(url, json=payload)
        except httpx.TransportError as exc:
            raise TelegramError("telegram_network_error", retryable=True) from exc

        if response.status_code == 429:
            try:
                body = response.json()
            except ValueError:
                body = None
            raise TelegramError(
                "telegram_rate_limited",
                retryable=True,
                retry_after=self._retry_after(
                    response,
                    body if isinstance(body, dict) else None,
                ),
            )
        if response.status_code >= 500:
            raise TelegramError("telegram_server_error", retryable=True)
        if response.status_code >= 400:
            raise TelegramError(
                f"telegram_http_{response.status_code}",
                retryable=False,
            )
        if response.status_code != 200:
            raise TelegramError(
                f"telegram_unexpected_http_{response.status_code}",
                retryable=False,
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise TelegramError("telegram_invalid_response", retryable=True) from exc
        if not isinstance(body, dict) or body.get("ok") is not True:
            error_code = body.get("error_code") if isinstance(body, dict) else None
            if error_code == 429:
                raise TelegramError(
                    "telegram_rate_limited",
                    retryable=True,
                    retry_after=self._retry_after(response, body),
                )
            retryable = isinstance(error_code, int) and error_code >= 500
            code = f"telegram_api_error_{error_code}" if error_code else "telegram_api_error"
            raise TelegramError(code, retryable=retryable)

    @staticmethod
    def _retry_after(
        response: httpx.Response,
        body: dict[str, object] | None = None,
    ) -> float | None:
        if body is not None:
            parameters = body.get("parameters")
            if isinstance(parameters, dict):
                value = parameters.get("retry_after")
                if isinstance(value, (int, float)) and value > 0:
                    return float(value)
        header_value = response.headers.get("Retry-After")
        if header_value is None:
            return None
        try:
            seconds = float(header_value)
        except ValueError:
            return None
        return seconds if seconds > 0 else None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "TelegramClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
