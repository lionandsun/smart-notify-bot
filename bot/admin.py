import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes
from . import db, utils

logger = logging.getLogger(__name__)

async def _admin_guard(update, context):
    msg, user, chat = update.effective_message, update.effective_user, update.effective_chat
    if not msg or not user: return False
    if chat and chat.type != "private":
        await msg.reply_text("Use admin commands in private chat.")
        return False
    await db.upsert_user(user.id, user.username, user.first_name, user.last_name)
    if not utils.is_admin(user.id):
        await msg.reply_text("Admin only.")
        return False
    return True

async def stats(update, context):
    if not await _admin_guard(update, context): return
    msg = update.effective_message
    if not msg: return
    data = await db.get_stats()
    await msg.reply_text(
        f"📊 Bot Statistics\n\n"
        f"Users: {data['users']}\n"
        f"Paid: {data['paid_users']}\n"
        f"Active keywords: {data['active_keywords']}\n"
        f"Notifs today: {data['notifications_today']}"
    )

async def broadcast(update, context):
    if not await _admin_guard(update, context): return
    msg = update.effective_message
    if not msg: return
    text = " ".join(context.args).strip() if context.args else (msg.reply_to_message.text or "") if msg.reply_to_message else ""
    if not text:
        await msg.reply_text("Usage: /broadcast <message>")
        return
    await msg.reply_text("📤 Broadcasting...")
    user_ids = await db.get_all_user_ids()
    success, failed = 0, 0
    for uid in user_ids:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 {text}")
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    await msg.reply_text(f"Done.\nSent: {success}\nFailed: {failed}")
