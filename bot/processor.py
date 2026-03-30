import re
import ipaddress
from dataclasses import dataclass, field
import httpx
from telegram import Message, Bot

URL_RE = re.compile(r"https?://[^\s]+")

_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / AWS IMDSv1
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _is_safe_url(url: str) -> bool:
    """Return False for private/loopback addresses (SSRF protection)."""
    try:
        from urllib.parse import urlparse
        import socket
        host = urlparse(url).hostname
        if not host:
            return False
        ip = ipaddress.ip_address(socket.gethostbyname(host))
        return not any(ip in net for net in _PRIVATE_NETS)
    except Exception:
        return False


@dataclass
class ProcessedMessage:
    text: str | None
    image_bytes: bytes | None
    content_type: str  # text | photo | url | forward | mixed
    fetched_urls: dict[str, str] = field(default_factory=dict)  # url -> page text
    forward_meta: str | None = None
    author_name: str = ""
    author_id: int = 0
    chat_id: int = 0
    message_id: int = 0


class MessageProcessor:
    def __init__(self, settings) -> None:
        self._settings = settings

    async def process(self, message: Message, bot: Bot | None = None) -> ProcessedMessage:
        text = message.text or message.caption or ""
        author_name = getattr(message.from_user, "full_name", "") or ""
        author_id = getattr(message.from_user, "id", 0) or 0

        result = ProcessedMessage(
            text=text,
            image_bytes=None,
            content_type="text",
            author_name=author_name,
            author_id=author_id,
            chat_id=message.chat_id,
            message_id=message.message_id,
        )

        # Detect forward
        if getattr(message, "forward_origin", None):
            fo = message.forward_origin
            origin = (
                getattr(fo, "sender_user_name", None)
                or (getattr(fo, "chat", None) and getattr(fo.chat, "title", None))
                or getattr(fo, "sender_chat", None) and getattr(fo.sender_chat, "title", None)
                or "unknown"
            )
            result.forward_meta = f"[Forwarded from {origin}]"
            result.content_type = "forward"

        # Detect photo
        if message.photo:
            if bot:
                photo = message.photo[-1]  # highest resolution
                f = await bot.get_file(photo.file_id)
                result.image_bytes = bytes(await f.download_as_bytearray())
            if not result.forward_meta:
                result.content_type = "photo"
                if result.image_bytes and text:
                    result.content_type = "mixed"

        # Detect URLs in text
        urls = URL_RE.findall(text)
        urls = [u.rstrip(".,!?;:)\"'") for u in urls]
        if urls:
            max_links = await self._settings.get("max_links_per_message", default=3)
            fetched: dict[str, str] = {}
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                for url in urls[:max_links]:
                    if not _is_safe_url(url):
                        fetched[url] = "[blocked: internal address]"
                        continue
                    try:
                        resp = await client.get(url)
                        fetched[url] = _extract_text(resp.text)
                    except Exception:
                        fetched[url] = "[could not fetch]"
            result.fetched_urls = fetched
            if not message.photo and not result.forward_meta:
                result.content_type = "url"

        return result


def _extract_text(html: str) -> str:
    """Naive HTML -> plain text: strip tags, collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:3000]  # cap to avoid huge context
