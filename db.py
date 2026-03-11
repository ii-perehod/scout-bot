import aiosqlite
from config import DB_PATH


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                title TEXT DEFAULT '',
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT UNIQUE NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS finds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                message_id INTEGER,
                text TEXT NOT NULL,
                link TEXT DEFAULT '',
                category TEXT DEFAULT '',
                is_free INTEGER DEFAULT 1,
                found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(channel, message_id)
            )
        """)
        await db.commit()


async def add_channel(username: str, title: str = "") -> bool:
    username = username.lstrip("@").lower()
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO channels (username, title) VALUES (?, ?)",
                (username, title),
            )
            await db.commit()
        return True
    except aiosqlite.IntegrityError:
        return False


async def remove_channel(username: str) -> bool:
    username = username.lstrip("@").lower()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM channels WHERE username = ?", (username,)
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_channels() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT username, title FROM channels ORDER BY added_at")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def add_keyword(word: str) -> bool:
    word = word.lower().strip()
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO keywords (word) VALUES (?)", (word,))
            await db.commit()
        return True
    except aiosqlite.IntegrityError:
        return False


async def remove_keyword(word: str) -> bool:
    word = word.lower().strip()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM keywords WHERE word = ?", (word,))
        await db.commit()
        return cursor.rowcount > 0


async def get_keywords() -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT word FROM keywords ORDER BY word")
        rows = await cursor.fetchall()
        return [r[0] for r in rows]


async def save_find(channel: str, message_id: int, text: str, link: str = "",
                    category: str = "", is_free: bool = True) -> bool:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO finds (channel, message_id, text, link, category, is_free)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (channel, message_id, text, link, category, int(is_free)),
            )
            await db.commit()
        return True
    except aiosqlite.IntegrityError:
        return False


async def search_catalog(query: str = "", free_only: bool = False) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        sql = "SELECT * FROM finds WHERE 1=1"
        params = []
        if query:
            sql += " AND text LIKE ?"
            params.append(f"%{query}%")
        if free_only:
            sql += " AND is_free = 1"
        sql += " ORDER BY found_at DESC LIMIT 20"
        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_recent_finds(days: int = 7) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM finds
               WHERE found_at >= datetime('now', ?)
               ORDER BY found_at DESC""",
            (f"-{days} days",),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM finds")
        total = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) FROM finds WHERE is_free = 1")
        free = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT category, COUNT(*) as cnt FROM finds GROUP BY category ORDER BY cnt DESC"
        )
        by_category = await cursor.fetchall()

        return {
            "total": total,
            "free": free,
            "paid": total - free,
            "by_category": by_category,
        }


async def has_any_finds() -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM finds")
        count = (await cursor.fetchone())[0]
        return count > 0
