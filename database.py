import aiosqlite
import asyncio
from datetime import datetime, timedelta
import json

class Database:
    def __init__(self, db_path="bot_data.db"):
        self.db_path = db_path

    async def initialize(self):
        async with aiosqlite.connect(self.db_path) as db:
            # Logs Table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    user_id INTEGER,
                    action TEXT,
                    details TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Warnings Table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    user_id INTEGER,
                    moderator_id INTEGER,
                    reason TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Voice Activity Table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS voice_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    user_id INTEGER,
                    channel_id INTEGER,
                    action TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Settings Table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    guild_id INTEGER,
                    key TEXT,
                    value TEXT,
                    PRIMARY KEY (guild_id, key)
                )
            ''')
            # Voice Sessions Table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS voice_sessions (
                    guild_id INTEGER,
                    user_id INTEGER,
                    join_time DATETIME,
                    PRIMARY KEY (guild_id, user_id)
                )
            ''')
            
            # Forced migration for duration column
            try:
                await db.execute("ALTER TABLE voice_activity ADD COLUMN duration TEXT")
                print("[DB] Колонка duration успешно добавлена.")
            except:
                pass 

            await db.commit()
            print("База данных SQLite инициализирована.")

    async def log_event(self, guild_id, user_id, action, details):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO logs (guild_id, user_id, action, details) VALUES (?, ?, ?, ?)",
                (guild_id, user_id, action, details)
            )
            await db.commit()

    async def add_warning(self, guild_id, user_id, moderator_id, reason):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)",
                (guild_id, user_id, moderator_id, reason)
            )
            await db.commit()

    async def get_warnings(self, guild_id, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT id, moderator_id, reason, timestamp FROM warnings WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id)
            ) as cursor:
                return await cursor.fetchall()

    async def delete_warning(self, warning_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM warnings WHERE id = ?", (warning_id,))
            await db.commit()

    async def log_voice(self, guild_id, user_id, channel_id, action, duration=None):
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(
                    "INSERT INTO voice_activity (guild_id, user_id, channel_id, action, duration) VALUES (?, ?, ?, ?, ?)",
                    (guild_id, user_id, channel_id, action, duration)
                )
            except aiosqlite.OperationalError:
                # Fallback if duration column is still missing
                await db.execute(
                    "INSERT INTO voice_activity (guild_id, user_id, channel_id, action) VALUES (?, ?, ?, ?)",
                    (guild_id, user_id, channel_id, action)
                )
            await db.commit()

    async def save_voice_entry(self, guild_id, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO voice_sessions (guild_id, user_id, join_time) VALUES (?, ?, ?)",
                (guild_id, user_id, datetime.now().isoformat())
            )
            await db.commit()

    async def pop_voice_entry(self, guild_id, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT join_time FROM voice_sessions WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    await db.execute("DELETE FROM voice_sessions WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
                    await db.commit()
                    return row[0]
                return None

    async def set_setting(self, guild_id, key, value):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO settings (guild_id, key, value) VALUES (?, ?, ?)",
                (guild_id, key, str(value))
            )
            await db.commit()

    async def get_setting(self, guild_id, key, default=None):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT value FROM settings WHERE guild_id = ? AND key = ?",
                (guild_id, key)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else default

    async def cleanup_logs(self):
        thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM logs WHERE timestamp < ?", (thirty_days_ago,))
            await db.execute("DELETE FROM voice_activity WHERE timestamp < ?", (thirty_days_ago,))
            await db.commit()
            
    async def get_user_logs(self, guild_id, user_id, limit=10):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT action, details, timestamp FROM logs WHERE guild_id = ? AND user_id = ? ORDER BY timestamp DESC LIMIT ?",
                (guild_id, user_id, limit)
            ) as cursor:
                return await cursor.fetchall()
