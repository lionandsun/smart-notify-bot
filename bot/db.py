import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator
import aiosqlite
import config

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT, first_name TEXT, last_name TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS subscriptions (
    user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    tier TEXT NOT NULL DEFAULT 'free' CHECK (tier IN ('free', 'paid')),
    tx_hash TEXT, verified_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    keyword TEXT NOT NULL COLLATE NOCASE,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, keyword)
);
CREATE TABLE IF NOT EXISTS daily_usage (
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    usage_date TEXT NOT NULL,
    notification_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, usage_date)
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword_id INTEGER NOT NULL REFERENCES keywords(id) ON DELETE CASCADE,
    item_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'sent',
    sent_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (keyword_id, item_hash)
);
CREATE TABLE IF NOT EXISTS payments (
    tx_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    amount_usdt REAL NOT NULL, status TEXT NOT NULL,
    raw_response TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

@asynccontextmanager
async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON;")
        await conn.execute("PRAGMA journal_mode = WAL;")
        try:
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise

async def init_db():
    async with get_db() as conn:
        await conn.executescript(SCHEMA)
    logger.info("Database initialized at %s", config.DATABASE_PATH)

def _today_utc():
    return datetime.now(timezone.utc).date().isoformat()

async def upsert_user(user_id, username=None, first_name=None, last_name=None):
    async with get_db() as conn:
        await conn.execute("INSERT INTO users (user_id, username, first_name, last_name) VALUES (?, ?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET username=COALESCE(excluded.username, users.username), first_name=COALESCE(excluded.first_name, users.first_name), last_name=COALESCE(excluded.last_name, users.last_name), updated_at=datetime('now')", (user_id, username, first_name, last_name))
        await conn.execute("INSERT OR IGNORE INTO subscriptions (user_id) VALUES (?)", (user_id,))

async def get_subscription(user_id):
    async with get_db() as conn:
        await conn.execute("INSERT OR IGNORE INTO subscriptions (user_id) VALUES (?)", (user_id,))
        cur = await conn.execute("SELECT tier, tx_hash, verified_at, created_at, updated_at FROM subscriptions WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else {"tier": "free", "tx_hash": None, "verified_at": None, "created_at": None, "updated_at": None}

async def activate_paid_subscription(user_id, tx_hash):
    async with get_db() as conn:
        await conn.execute("INSERT OR IGNORE INTO subscriptions (user_id) VALUES (?)", (user_id,))
        await conn.execute("UPDATE subscriptions SET tier='paid', tx_hash=?, verified_at=datetime('now'), updated_at=datetime('now') WHERE user_id=?", (tx_hash, user_id))

async def add_keyword(user_id, keyword):
    keyword = " ".join(keyword.split())
    if len(keyword) < 2 or len(keyword) > 100:
        return "invalid"
    async with get_db() as conn:
        cur = await conn.execute("SELECT id, is_active FROM keywords WHERE user_id=? AND keyword=?", (user_id, keyword))
        row = await cur.fetchone()
        if row:
            if row["is_active"] == 1: return "exists"
            await conn.execute("UPDATE keywords SET is_active=1, created_at=datetime('now') WHERE id=?", (row["id"],))
            return "reactivated"
        cur = await conn.execute("SELECT COUNT(*) FROM keywords WHERE user_id=? AND is_active=1", (user_id,))
        count_row = await cur.fetchone()
        if count_row and count_row[0] >= config.MAX_KEYWORDS_PER_USER:
            return "limit"
        await conn.execute("INSERT INTO keywords (user_id, keyword) VALUES (?, ?)", (user_id, keyword))
        return "added"

async def get_keywords_by_user(user_id):
    async with get_db() as conn:
        cur = await conn.execute("SELECT id, keyword, created_at FROM keywords WHERE user_id=? AND is_active=1 ORDER BY keyword ASC", (user_id,))
        return [dict(row) for row in await cur.fetchall()]

async def get_active_keywords():
    async with get_db() as conn:
        cur = await conn.execute("SELECT id, user_id, keyword FROM keywords WHERE is_active=1 ORDER BY id ASC")
        return [dict(row) for row in await cur.fetchall()]

async def remove_keyword(user_id, identifier):
    identifier = identifier.strip()
    if not identifier: return False
    async with get_db() as conn:
        if identifier.isdigit():
            cur = await conn.execute("UPDATE keywords SET is_active=0 WHERE user_id=? AND id=? AND is_active=1", (user_id, int(identifier)))
            if cur.rowcount > 0: return True
        cur = await conn.execute("UPDATE keywords SET is_active=0 WHERE user_id=? AND keyword=? AND is_active=1", (user_id, identifier))
        return cur.rowcount > 0

async def get_daily_notification_count(user_id):
    async with get_db() as conn:
        cur = await conn.execute("SELECT notification_count FROM daily_usage WHERE user_id=? AND usage_date=?", (user_id, _today_utc()))
        row = await cur.fetchone()
        return row["notification_count"] if row else 0

async def has_alert(keyword_id, item_hash):
    async with get_db() as conn:
        cur = await conn.execute("SELECT 1 FROM alerts WHERE keyword_id=? AND item_hash=? LIMIT 1", (keyword_id, item_hash))
        return (await cur.fetchone()) is not None

async def mark_alert(keyword_id, item_hash, status="sent"):
    async with get_db() as conn:
        await conn.execute("INSERT INTO alerts (keyword_id, item_hash, status) VALUES (?, ?, ?) ON CONFLICT(keyword_id, item_hash) DO UPDATE SET status=excluded.status, sent_at=datetime('now')", (keyword_id, item_hash, status))

async def record_notification_and_mark_alert(user_id, keyword_id, item_hash):
    async with get_db() as conn:
        await conn.execute("INSERT INTO daily_usage (user_id, usage_date, notification_count) VALUES (?, ?, 1) ON CONFLICT(user_id, usage_date) DO UPDATE SET notification_count=notification_count+1", (user_id, _today_utc()))
        await conn.execute("INSERT INTO alerts (keyword_id, item_hash, status) VALUES (?, ?, 'sent') ON CONFLICT(keyword_id, item_hash) DO UPDATE SET status='sent', sent_at=datetime('now')", (keyword_id, item_hash))

async def payment_is_confirmed(tx_hash):
    async with get_db() as conn:
        cur = await conn.execute("SELECT 1 FROM payments WHERE tx_hash=? AND status='confirmed' LIMIT 1", (tx_hash,))
        return (await cur.fetchone()) is not None

async def record_payment(tx_hash, user_id, amount_usdt, status, raw_response):
    async with get_db() as conn:
        await conn.execute("INSERT INTO payments (tx_hash, user_id, amount_usdt, status, raw_response) VALUES (?, ?, ?, ?, ?) ON CONFLICT(tx_hash) DO UPDATE SET amount_usdt=excluded.amount_usdt, status=excluded.status, raw_response=excluded.raw_response", (tx_hash, user_id, amount_usdt, status, raw_response))

async def get_all_user_ids():
    async with get_db() as conn:
        cur = await conn.execute("SELECT user_id FROM users ORDER BY user_id ASC")
        return [row["user_id"] for row in await cur.fetchall()]

async def get_stats():
    async with get_db() as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM users")
        users = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM subscriptions WHERE tier='paid'")
        paid = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM keywords WHERE is_active=1")
        keywords = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COALESCE(SUM(notification_count),0) FROM daily_usage WHERE usage_date=?", (_today_utc(),))
        notifs = (await cur.fetchone())[0]
        return {"users": users, "paid_users": paid, "active_keywords": keywords, "notifications_today": notifs}
