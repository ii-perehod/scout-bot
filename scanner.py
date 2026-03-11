"""Standalone scanner for GitHub Actions.

Reads public Telegram channels via t.me web preview (no Telethon needed).
Filters by keywords, sends new finds to admin via Telegram Bot API.
Saves results to finds.json.
"""

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError
from html.parser import HTMLParser

# ── Config (from .env or environment) ───────────────────
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

FINDS_FILE = Path(__file__).parent / "finds.json"
CHANNELS_FILE = Path(__file__).parent / "channels.json"

# ── Keywords ────────────────────────────────────────────
KEYWORDS = [
    "github.com", "open source", "бесплатно", "инструмент", "скилл",
    "утилита", "расширение", "плагин", "шаблон", "фреймворк",
    "генератор", "конструктор", "сервис", "тул", "tool",
    "cursor", "make.com", "n8n", "zapier", "vercel", "supabase",
    "netlify", "railway", "render", "firebase",
    "notion", "airtable", "figma",
    "gpt", "claude", "gemini", "midjourney", "stable diffusion",
    "нейросет", "llm", "chatgpt", "openai", "anthropic",
    "langchain", "llamaindex", "autogen", "crewai",
    "openrouter", "groq", "ollama", "huggingface",
    "api", "скрипт", "парсер", "бот", "автоматизация",
    "python", "javascript", "node.js", "docker",
    "seo", "аналитик", "метрик",
    "репозиторий", "npm install", "pip install",
    "git clone", "подборка", "топ-",
]


# ── HTML parser for t.me/s/ widget ─────────────────────
class TelegramWidgetParser(HTMLParser):
    """Parse posts from t.me/s/channel_name (public web widget)."""

    def __init__(self):
        super().__init__()
        self.posts = []
        self._current_post = None
        self._in_message = False
        self._in_text = False
        self._current_text = ""
        self._current_link = ""

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")

        # Each post is in a div with class "tgme_widget_message_wrap"
        if tag == "div" and "tgme_widget_message " in cls:
            data_post = attrs_dict.get("data-post", "")
            self._current_post = data_post
            self._current_link = f"https://t.me/{data_post}" if data_post else ""

        if tag == "div" and "tgme_widget_message_text" in cls:
            self._in_text = True
            self._current_text = ""

        # Capture links inside message text
        if self._in_text and tag == "a":
            href = attrs_dict.get("href", "")
            if href and href.startswith("http"):
                self._current_text += f" {href} "

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


def fetch_channel_posts(username: str) -> list[dict]:
    """Fetch recent posts from a public channel via t.me/s/ web widget."""
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


# ── Helpers ─────────────────────────────────────────────
def extract_links(text: str) -> list[str]:
    return re.findall(r"https?://[^\s)<>\"]+", text)


def matches_keywords(text: str) -> bool:
    t = text.lower()
    return "github.com/" in t or any(kw in t for kw in KEYWORDS)


def guess_category(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["seo", "выдач", "индекс"]):
        return "SEO"
    if any(w in t for w in ["бот", "bot", "telegram"]):
        return "Бот"
    if any(w in t for w in ["автоматиз", "make.com", "n8n", "zapier"]):
        return "Автоматизация"
    if any(w in t for w in ["github", "open source", "репозитор"]):
        return "Open Source"
    if any(w in t for w in ["gpt", "claude", "нейросет", "llm", "midjourney", "gemini"]):
        return "ИИ"
    if any(w in t for w in ["дизайн", "figma"]):
        return "Дизайн"
    if any(w in t for w in ["парс", "scraping"]):
        return "Парсинг"
    if any(w in t for w in ["vercel", "deploy", "хостинг"]):
        return "Хостинг"
    return "Другое"


def guess_free(text: str) -> bool:
    t = text.lower()
    if any(w in t for w in ["бесплатн", "free", "open source"]):
        return True
    if any(w in t for w in ["платн", "подписк", "тариф", "$", "₽"]):
        return False
    return True


def send_telegram(text: str):
    """Send message to admin via Telegram Bot API."""
    if not BOT_TOKEN or not ADMIN_ID:
        print(f"[would send]: {text[:200]}")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = json.dumps({
        "chat_id": ADMIN_ID,
        "text": text[:4096],
        "disable_web_page_preview": True,
    }).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        urlopen(req, timeout=10)
    except Exception as e:
        print(f"Telegram send error: {e}")


def load_existing_finds() -> dict:
    if FINDS_FILE.exists():
        with open(FINDS_FILE, "r", encoding="utf-8") as f:
            items = json.load(f)
        return {item["post_id"]: item for item in items if "post_id" in item}
    return {}


def save_finds(finds_dict: dict):
    items = list(finds_dict.values())
    items.sort(key=lambda x: x.get("found_at", ""), reverse=True)
    with open(FINDS_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def load_channels() -> list[str]:
    if CHANNELS_FILE.exists():
        with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


# ── Main scan ───────────────────────────────────────────
def scan():
    channels = load_channels()
    if not channels:
        print("No channels in channels.json")
        return

    existing = load_existing_finds()
    new_finds = []

    for username in channels:
        print(f"Scanning @{username}...")
        posts = fetch_channel_posts(username)
        print(f"  Found {len(posts)} posts")

        for post in posts:
            if post["post_id"] in existing:
                continue
            if not matches_keywords(post["text"]):
                continue

            links = extract_links(post["text"])
            find = {
                "post_id": post["post_id"],
                "channel": username,
                "text": post["text"][:1000],
                "link": links[0] if links else post["link"],
                "tg_link": post["link"],
                "category": guess_category(post["text"]),
                "is_free": guess_free(post["text"]),
                "found_at": datetime.now(timezone.utc).isoformat(),
            }
            existing[post["post_id"]] = find
            new_finds.append(find)

    save_finds(existing)

    if new_finds:
        header = f"Скаут: {len(new_finds)} новых находок!\n\n"
        messages = []
        current = header

        for find in new_finds[:20]:
            free_label = "бспл" if find["is_free"] else "платн"
            entry = (
                f"[{find['category']}] [{free_label}]\n"
                f"{find['text'][:200]}...\n"
                f"{find['tg_link']}\n\n"
            )
            if len(current) + len(entry) > 4000:
                messages.append(current)
                current = entry
            else:
                current += entry

        if current:
            messages.append(current)

        for msg in messages[:5]:
            send_telegram(msg)

        if len(new_finds) > 20:
            send_telegram(f"...и ещё {len(new_finds) - 20} находок.")

        print(f"Done: {len(new_finds)} new finds sent to Telegram")
    else:
        print("No new finds matching keywords")


if __name__ == "__main__":
    scan()
