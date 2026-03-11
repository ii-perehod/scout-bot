"""Channel monitor — reads public channels via t.me/s/ web widget.

No Telethon, no API keys needed. Only works with PUBLIC channels.
"""

import re
from urllib.request import Request, urlopen
from urllib.error import URLError
from html.parser import HTMLParser

from config import DEFAULT_KEYWORDS
import db


class TelegramWidgetParser(HTMLParser):
    """Parse posts from t.me/s/channel_name."""

    def __init__(self):
        super().__init__()
        self.posts = []
        self._current_post = None
        self._in_text = False
        self._current_text = ""
        self._current_link = ""

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")

        if tag == "div" and "tgme_widget_message " in cls:
            data_post = attrs_dict.get("data-post", "")
            self._current_post = data_post
            self._current_link = f"https://t.me/{data_post}" if data_post else ""

        if tag == "div" and "tgme_widget_message_text" in cls:
            self._in_text = True
            self._current_text = ""

        if self._in_text and tag == "a":
            href = attrs_dict.get("href", "")
            if href and href.startswith("http"):
                self._current_text += f" {href} "

        if self._in_text and tag == "br":
            self._current_text += "\n"

    def handle_endtag(self, tag):
        if tag == "div" and self._in_text:
            self._in_text = False
            if self._current_post and self._current_text.strip():
                self.posts.append({
                    "post_id": self._current_post,
                    "text": self._current_text.strip(),
                    "link": self._current_link,
                })

    def handle_data(self, data):
        if self._in_text:
            self._current_text += data


def _fetch_channel_posts(username: str) -> list[dict]:
    """Fetch recent posts from public channel via web widget."""
    url = f"https://t.me/s/{username}"
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9",
    })
    try:
        with urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except (URLError, TimeoutError) as e:
        print(f"Error fetching @{username}: {e}")
        return []

    parser = TelegramWidgetParser()
    parser.feed(html)
    return parser.posts


def _extract_links(text: str) -> list[str]:
    return re.findall(r"https?://[^\s)<>\"]+", text)


def _matches_keywords(text: str, keywords: list[str]) -> bool:
    text_lower = text.lower()
    return "github.com/" in text_lower or any(kw in text_lower for kw in keywords)


def _guess_category(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["seo", "выдач", "индекс", "ранжир"]):
        return "SEO"
    if any(w in t for w in ["бот", "bot", "telegram", "телеграм"]):
        return "Бот"
    if any(w in t for w in ["автоматиз", "make.com", "n8n", "zapier", "no-code"]):
        return "Автоматизация"
    if any(w in t for w in ["github", "open source", "репозитор", "git clone"]):
        return "Open Source"
    if any(w in t for w in ["gpt", "claude", "нейросет", "llm", "midjourney", "gemini", "openai"]):
        return "ИИ"
    if any(w in t for w in ["дизайн", "figma", "canva"]):
        return "Дизайн"
    if any(w in t for w in ["парс", "scraping", "скрап"]):
        return "Парсинг"
    if any(w in t for w in ["vercel", "deploy", "хостинг", "сервер"]):
        return "Хостинг"
    if any(w in t for w in ["python", "javascript", "node", "скрипт"]):
        return "Код"
    return "Другое"


def _guess_free(text: str) -> bool:
    t = text.lower()
    if any(w in t for w in ["бесплатн", "free", "open source"]):
        return True
    if any(w in t for w in ["платн", "подписк", "тариф", "$", "₽"]):
        return False
    return True


async def scan_channels(days: int = 3) -> list[dict]:
    """Scan all saved channels for posts matching keywords.

    Uses t.me/s/ web widget — shows ~20 most recent posts.
    """
    channels = await db.get_channels()
    if not channels:
        return []

    custom_keywords = await db.get_keywords()
    keywords = list(set(DEFAULT_KEYWORDS + custom_keywords))
    new_finds = []

    for ch in channels:
        username = ch["username"]
        posts = _fetch_channel_posts(username)

        for post in posts:
            if not _matches_keywords(post["text"], keywords):
                continue

            links = _extract_links(post["text"])
            link = links[0] if links else post["link"]
            parts = post["post_id"].split("/")
            msg_id = int(parts[-1]) if parts[-1].isdigit() else hash(post["post_id"])

            saved = await db.save_find(
                channel=username,
                message_id=msg_id,
                text=post["text"][:1000],
                link=link,
                category=_guess_category(post["text"]),
                is_free=_guess_free(post["text"]),
            )
            if saved:
                new_finds.append({
                    "channel": username,
                    "text": post["text"][:1000],
                    "link": link,
                    "tg_link": post["link"],
                    "category": _guess_category(post["text"]),
                    "is_free": _guess_free(post["text"]),
                })

    return new_finds
