import hashlib
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
import httpx
from telegram.error import Forbidden, TelegramError
from telegram.ext import Application
import config
from . import db

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class SourceItem:
    id: str
    text: str
    url: Optional[str]
    source: str

async def fetch_source_items(active_keywords):
    if config.SOURCE_TYPE == "http" and config.SOURCE_URL:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(config.SOURCE_URL)
                response.raise_for_status()
                text = response.text
                item_hash = hashlib.sha256(text.encode()).hexdigest()
                return [SourceItem(id=item_hash, text=text, url=config.SOURCE_URL, source="http")]
        except Exception:
            logger.exception("Failed to fetch HTTP source.")
            return []
    return [_mock_source_item(active_keywords)]

def _mock_source_item(active_keywords):
    now = datetime.now(timezone.utc)
    minute_token = now.strftime("%Y%m%d%H%M")
    seed = int(hashlib.sha256(minute_token.encode()).hexdigest(), 16)
    rng = random.Random(seed)
    terms = list(active_keywords) if active_keywords else list(config.MOCK_DEFAULT_TERMS)
    if rng.random() <= config.MOCK_MATCH_PROBABILITY and terms:
        keyword = rng.choice(terms)
    else:
        keyword = rng.choice(config.MOCK_DEFAULT_TERMS)
    text = f"[MOCK] {now.isoformat()} | signal={keyword}\nSimulated source mentioning {keyword.upper()}."
    item_hash = hashlib.sha256(text.encode()).hexdigest()
    return SourceItem(id=item_hash, text=text, url=None, source="mock")

def _build_alert_message(keyword, item):
    lines = [f"🔔 Keyword alert: {keyword}"]
    if item.url: lines.append(f"Source: {item.url}")
    snippet = item.text.strip()
    if len(snippet) > 700: snippet = snippet[:700] + "..."
    lines.append(snippet)
    return "\n\n".join(lines)

async def monitoring_cycle(application):
    try:
        keywords = await db.get_active_keywords()
        if not keywords: return
        active_terms = [row["keyword"] for row in keywords]
        items = await fetch_source_items(active_terms)
        if not items: return
        for kw_row in keywords:
            keyword_id, user_id, keyword = kw_row["id"], kw_row["user_id"], kw_row["keyword"].lower()
            for item in items:
                if keyword not in item.text.lower(): continue
                if await db.has_alert(keyword_id, item.id): continue
                subscription = await db.get_subscription(user_id)
                if subscription["tier"] != "paid":
                    used_today = await db.get_daily_notification_count(user_id)
                    if used_today >= config.FREE_DAILY_NOTIFICATION_LIMIT:
                        await db.mark_alert(keyword_id, item.id, status="suppressed")
                        continue
                message = _build_alert_message(kw_row["keyword"], item)
                try:
                    await application.bot.send_message(chat_id=user_id, text=message)
                except Forbidden:
                    await db.mark_alert(keyword_id, item.id, status="suppressed")
                    continue
                except TelegramError:
                    continue
                await db.record_notification_and_mark_alert(user_id, keyword_id, item.id)
    except Exception:
        logger.exception("Error in monitoring cycle.")
