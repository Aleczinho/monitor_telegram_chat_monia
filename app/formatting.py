import html
from datetime import UTC, datetime
from urllib.parse import urlsplit


def escape_text(value: str, limit: int = 1200) -> str:
    clipped = value[:limit]
    if len(value) > limit:
        clipped += "…"
    return html.escape(clipped, quote=True).replace("\n", "<br>")


def github_link(url: object | None, label: str) -> str:
    if url is None:
        return ""
    parsed = urlsplit(str(url))
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
    ):
        return ""
    safe_url = html.escape(parsed.geturl(), quote=True)
    return f'🔗 <a href="{safe_url}">{escape_text(label, 100)}</a>'


def format_timestamp(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def optional_line(label: str, value: str | None) -> str:
    if not value:
        return ""
    return f"{label} {value}"
