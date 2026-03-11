"""Scout Bot — Telegram bot that monitors channels for useful dev tools.

Runs on a server (Oracle Cloud Free Tier).
Auto-scans channels on schedule, sends digest to admin.
"""

import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message

from config import BOT_TOKEN, ADMIN_ID, SCAN_INTERVAL_HOURS, FIRST_SCAN_DAYS, REGULAR_SCAN_DAYS
import db
import monitor
import sync

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Track if first scan has been done
_first_scan_done = False


def admin_only(handler):
    """Allow only admin to use the bot."""
    async def wrapper(message: Message, *args, **kwargs):
        if message.from_user.id != ADMIN_ID:
            await message.answer("Бот доступен только владельцу.")
            return
        return await handler(message, *args, **kwargs)
    wrapper.__name__ = handler.__name__
    return wrapper


def _format_find(find: dict, short: bool = False) -> str:
    """Format a single find for display."""
    free_label = "бспл" if find.get("is_free") else "платн"
    cat = find.get("category", "")
    channel = find.get("channel", "")
    text = find.get("text", "")
    link = find.get("link", "")

    max_len = 150 if short else 300
    snippet = text[:max_len].replace("\n", " ")
    if len(text) > max_len:
        snippet += "..."

    return f"[{cat}] [{free_label}] @{channel}\n{snippet}\n{link}"


# ── /start ──────────────────────────────────────────────
@dp.message(Command("start"))
@admin_only
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я бот-скаут.\n\n"
        "Мониторю Telegram-каналы и ищу полезные инструменты для разработки.\n\n"
        "Управление каналами:\n"
        "  /add @channel — добавить канал\n"
        "  /remove @channel — убрать канал\n"
        "  /channels — список каналов\n\n"
        "Ключевые слова:\n"
        "  /keywords — текущие слова\n"
        "  /addkw слово — добавить\n"
        "  /rmkw слово — убрать\n\n"
        "Сканирование:\n"
        "  /scan — сканировать за 3 дня\n"
        "  /deepscan — сканировать за 2 месяца\n"
        "  /digest — дайджест за неделю\n"
        "  /find запрос — поиск в каталоге\n"
        "  /stats — статистика каталога\n\n"
        f"Автосканирование: каждые {SCAN_INTERVAL_HOURS}ч"
    )


# ── Channels ────────────────────────────────────────────
@dp.message(Command("add"))
@admin_only
async def cmd_add(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Укажи канал: /add @channel_name")
        return
    username = parts[1].strip().lstrip("@")
    if await db.add_channel(username):
        await message.answer(f"Канал @{username} добавлен.")
    else:
        await message.answer(f"@{username} уже в списке.")


@dp.message(Command("remove"))
@admin_only
async def cmd_remove(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Укажи канал: /remove @channel_name")
        return
    username = parts[1].strip().lstrip("@")
    if await db.remove_channel(username):
        await message.answer(f"Канал @{username} удалён.")
    else:
        await message.answer(f"@{username} не найден.")


@dp.message(Command("channels"))
@admin_only
async def cmd_channels(message: Message):
    channels = await db.get_channels()
    if not channels:
        await message.answer("Каналов пока нет. Добавь: /add @channel_name")
        return
    text = f"Каналы ({len(channels)}):\n" + "\n".join(
        f"  @{ch['username']}" + (f" ({ch['title']})" if ch["title"] else "")
        for ch in channels
    )
    await message.answer(text)


# ── Keywords ────────────────────────────────────────────
@dp.message(Command("keywords"))
@admin_only
async def cmd_keywords(message: Message):
    kws = await db.get_keywords()
    from config import DEFAULT_KEYWORDS
    text = f"Встроенные ({len(DEFAULT_KEYWORDS)}):\n"
    text += ", ".join(DEFAULT_KEYWORDS) + "\n\n"
    if kws:
        text += f"Свои ({len(kws)}): " + ", ".join(kws)
    else:
        text += "Своих пока нет. Добавь: /addkw слово"

    if len(text) > 4000:
        text = text[:4000] + "..."
    await message.answer(text)


@dp.message(Command("addkw"))
@admin_only
async def cmd_addkw(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Укажи слово: /addkw нейросеть")
        return
    word = parts[1].strip()
    if await db.add_keyword(word):
        await message.answer(f"Ключевое слово «{word}» добавлено.")
    else:
        await message.answer(f"«{word}» уже есть.")


@dp.message(Command("rmkw"))
@admin_only
async def cmd_rmkw(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Укажи слово: /rmkw слово")
        return
    word = parts[1].strip()
    if await db.remove_keyword(word):
        await message.answer(f"«{word}» удалено.")
    else:
        await message.answer(f"«{word}» не найдено.")


# ── Scan ────────────────────────────────────────────────
async def _do_scan(days: int, notify_chat_id: int | None = None):
    """Run scan and optionally notify admin."""
    channels = await db.get_channels()
    if not channels:
        if notify_chat_id:
            await bot.send_message(notify_chat_id, "Нет каналов для сканирования.")
        return []

    try:
        new_finds = await monitor.scan_channels(days=days)
    except Exception as e:
        logging.error(f"Scan error: {e}")
        if notify_chat_id:
            await bot.send_message(notify_chat_id, f"Ошибка сканирования: {e}")
        return []

    if notify_chat_id:
        if not new_finds:
            await bot.send_message(notify_chat_id, f"Сканирование за {days} дн. — новых находок нет.")
        else:
            await bot.send_message(
                notify_chat_id,
                f"Сканирование за {days} дн. — найдено {len(new_finds)} новых!"
            )
            for find in new_finds[:15]:
                try:
                    await bot.send_message(notify_chat_id, _format_find(find))
                except Exception:
                    pass
                await asyncio.sleep(0.3)  # avoid flood limit

            if len(new_finds) > 15:
                await bot.send_message(
                    notify_chat_id,
                    f"...и ещё {len(new_finds) - 15}. Команда /digest покажет всё."
                )

    return new_finds


@dp.message(Command("scan"))
@admin_only
async def cmd_scan(message: Message):
    await message.answer("Сканирую каналы за 3 дня...")
    await _do_scan(days=REGULAR_SCAN_DAYS, notify_chat_id=message.chat.id)


@dp.message(Command("deepscan"))
@admin_only
async def cmd_deepscan(message: Message):
    await message.answer(f"Глубокое сканирование за {FIRST_SCAN_DAYS} дней... Это займёт время.")
    await _do_scan(days=FIRST_SCAN_DAYS, notify_chat_id=message.chat.id)


# ── Digest ──────────────────────────────────────────────
@dp.message(Command("digest"))
@admin_only
async def cmd_digest(message: Message):
    finds = await db.get_recent_finds(days=7)
    if not finds:
        await message.answer("За неделю ничего не найдено. Попробуй /scan")
        return

    by_cat = {}
    for f in finds:
        cat = f["category"] or "Другое"
        by_cat.setdefault(cat, []).append(f)

    text = f"Дайджест за неделю: {len(finds)} находок\n\n"
    for cat, items in sorted(by_cat.items()):
        text += f"── {cat} ({len(items)}) ──\n"
        for item in items[:5]:
            text += _format_find(item, short=True) + "\n\n"
        if len(items) > 5:
            text += f"  ...ещё {len(items) - 5}\n\n"

    # Split long messages
    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts[:3]:
            await message.answer(part)
        if len(parts) > 3:
            await message.answer("...обрезано. Используй /find для точного поиска.")
    else:
        await message.answer(text)


# ── Search catalog ──────────────────────────────────────
@dp.message(Command("find"))
@admin_only
async def cmd_find(message: Message):
    parts = message.text.split(maxsplit=1)
    query = parts[1].strip() if len(parts) > 1 else ""

    finds = await db.search_catalog(query)
    if not finds:
        await message.answer("Ничего не найдено." + (" Попробуй другой запрос." if query else ""))
        return

    text = f"Результаты" + (f" по «{query}»" if query else "") + f": {len(finds)}\n\n"
    for f in finds:
        text += _format_find(f) + "\n\n"

    if len(text) > 4000:
        text = text[:4000] + "\n...обрезано. Уточни запрос."
    await message.answer(text)


# ── Stats ───────────────────────────────────────────────
@dp.message(Command("stats"))
@admin_only
async def cmd_stats(message: Message):
    stats = await db.get_stats()
    channels = await db.get_channels()
    text = (
        f"Статистика каталога:\n\n"
        f"Каналов: {len(channels)}\n"
        f"Всего находок: {stats['total']}\n"
        f"Бесплатных: {stats['free']}\n"
        f"Платных: {stats['paid']}\n\n"
        f"По категориям:\n"
    )
    for cat, count in stats["by_category"]:
        text += f"  {cat}: {count}\n"

    await message.answer(text)


# ── Auto-scan scheduler ────────────────────────────────
async def auto_scan_loop():
    """Background task: scan channels on schedule."""
    global _first_scan_done

    # Wait for bot to start
    await asyncio.sleep(10)

    while True:
        channels = await db.get_channels()
        if channels:
            # First run: deep scan
            if not _first_scan_done:
                has_finds = await db.has_any_finds()
                if not has_finds:
                    logging.info(f"First scan: {FIRST_SCAN_DAYS} days back")
                    await _do_scan(days=FIRST_SCAN_DAYS, notify_chat_id=ADMIN_ID)
                _first_scan_done = True
            else:
                logging.info(f"Auto-scan: {REGULAR_SCAN_DAYS} days back")
                new_finds = await _do_scan(days=REGULAR_SCAN_DAYS)
                # Only notify if something found
                if new_finds:
                    await bot.send_message(
                        ADMIN_ID,
                        f"Автосканирование: {len(new_finds)} новых находок! /digest"
                    )

        await asyncio.sleep(SCAN_INTERVAL_HOURS * 3600)


# ── Main ────────────────────────────────────────────────
async def main():
    await db.init_db()

    # Import finds from GitHub Actions (finds.json)
    imported = await sync.import_finds()
    if imported:
        logging.info(f"Imported {imported} finds from finds.json")

    logging.info("Scout Bot started")

    # Start auto-scan in background
    asyncio.create_task(auto_scan_loop())

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
