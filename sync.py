"""Sync finds.json (from GitHub Actions) into local SQLite database."""

import json
from pathlib import Path
import asyncio
import db


FINDS_FILE = Path(__file__).parent / "finds.json"


async def import_finds():
    """Import finds from JSON into SQLite (skips duplicates)."""
    if not FINDS_FILE.exists():
        print("finds.json not found, nothing to import")
        return 0

    with open(FINDS_FILE, "r", encoding="utf-8") as f:
        items = json.load(f)

    imported = 0
    for item in items:
        saved = await db.save_find(
            channel=item["channel"],
            message_id=item["message_id"],
            text=item["text"],
            link=item.get("link", ""),
            category=item.get("category", ""),
            is_free=item.get("is_free", True),
        )
        if saved:
            imported += 1

    return imported


async def export_finds():
    """Export SQLite finds to JSON (for pushing to GitHub)."""
    finds = await db.get_recent_finds(days=9999)
    items = []
    for f in finds:
        items.append({
            "channel": f["channel"],
            "message_id": f["message_id"],
            "text": f["text"],
            "link": f["link"],
            "category": f["category"],
            "is_free": bool(f["is_free"]),
            "found_at": f["found_at"] if isinstance(f["found_at"], str) else str(f["found_at"]),
        })

    with open(FINDS_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    return len(items)


if __name__ == "__main__":
    asyncio.run(db.init_db())
    count = asyncio.run(import_finds())
    print(f"Imported {count} new finds from finds.json")
