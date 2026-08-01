import functools
import json
import logging
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes
import config
from . import db, payments, utils

logger = logging.getLogger(__name__)

def private_only(handler):
    @functools.wraps(handler)
    async def wrapper(update, context):
        chat = update.effective_chat
        if chat and chat.type != "private":
            if update.effective_message:
                await update.effective_message.reply_text("Please open a private chat with me.")
            return
        return await handler(update, context)
    return wrapper

async def _track_user(update):
    user = update.effective_user
    if user:
        await db.upsert_user(user.id, user.username, user.first_name, user.last_name)

@private_only
async def start(update, context):
    msg = update.effective_message
    if not msg: return
    await _track_user(update)
    await msg.reply_text(
        "👋 Welcome to smart-notify-bot!\n\n"
        "I monitor sources and alert you when keywords appear.\n\n"
        "Commands:\n"
        "/subscribe - subscription status\n"
        "/notify <keyword> - add keyword alert\n"
        "/keywords - list active keywords\n"
        "/remove <id> - remove keyword\n"
        "/upgrade <tx_hash> - USDT TRC20 payment\n"
        "/help - show help"
    )

@private_only
async def help_command(update, context):
    msg = update.effective_message
    if not msg: return
    await _track_user(update)
    await msg.reply_text(
        "Commands:\n/start - welcome\n/subscribe - status\n/notify <kw> - add keyword\n/keywords - list keywords\n/remove <id> - remove keyword\n/upgrade <tx_hash> - upgrade\n\n"
        f"Free: {config.FREE_DAILY_NOTIFICATION_LIMIT} notifs/day\nPaid: unlimited"
    )

@private_only
async def subscribe(update, context):
    msg, user = update.effective_message, update.effective_user
    if not msg or not user: return
    await _track_user(update)
    sub = await db.get_subscription(user.id)
    if sub["tier"] == "paid":
        await msg.reply_text(f"✅ Subscription: PAID\nNotifications: unlimited\nVerified: {sub.get('verified_at', 'N/A')} UTC")
        return
    used = await db.get_daily_notification_count(user.id)
    await msg.reply_text(
        f"📦 Subscription: FREE\nDaily limit: {config.FREE_DAILY_NOTIFICATION_LIMIT}\nUsed today: {used}\n\n"
        f"Upgrade: {config.PAYMENT_AMOUNT_USDT} USDT (TRC20)\n"
        f"Send to: {config.PAYMENT_WALLET_ADDRESS}\nThen: /upgrade <TX_HASH>"
    )

@private_only
async def notify(update, context):
    msg, user = update.effective_message, update.effective_user
    if not msg or not user: return
    await _track_user(update)
    if not context.args:
        await msg.reply_text("Usage: /notify <keyword>\nExample: /notify bitcoin")
        return
    keyword = " ".join(context.args).strip()
    result = await db.add_keyword(user.id, keyword)
    responses = {
        "invalid": "Keyword must be 2-100 characters.",
        "limit": f"Max keywords reached: {config.MAX_KEYWORDS_PER_USER}",
        "exists": f"Already monitoring: {keyword}",
    }
    if result in responses:
        await msg.reply_text(responses[result])
        return
    text = f"✅ Keyword {'reactivated' if result == 'reactivated' else 'added'}: {keyword}"
    sub = await db.get_subscription(user.id)
    text += f"\n{'Paid: unlimited' if sub['tier'] == 'paid' else f'Free limit: {config.FREE_DAILY_NOTIFICATION_LIMIT}/day'}"
    await msg.reply_text(text)

@private_only
async def keywords(update, context):
    msg, user = update.effective_message, update.effective_user
    if not msg or not user: return
    await _track_user(update)
    rows = await db.get_keywords_by_user(user.id)
    if not rows:
        await msg.reply_text("No active keywords.\nAdd with: /notify <keyword>")
        return
    lines = ["Active keywords:"] + [f"{r['id']}: {r['keyword']}" for r in rows[:100]]
    lines.append("\nRemove: /remove <id>")
    await msg.reply_text("\n".join(lines))

@private_only
async def remove(update, context):
    msg, user = update.effective_message, update.effective_user
    if not msg or not user: return
    await _track_user(update)
    if not context.args:
        await msg.reply_text("Usage: /remove <id or keyword>")
        return
    identifier = " ".join(context.args).strip()
    removed = await db.remove_keyword(user.id, identifier)
    await msg.reply_text(f"✅ Removed: {identifier}" if removed else f"Not found: {identifier}")

@private_only
async def upgrade(update, context):
    msg, user = update.effective_message, update.effective_user
    if not msg or not user: return
    await _track_user(update)
    if not context.args:
        await msg.reply_text("Usage: /upgrade <TX_HASH>")
        return
    tx_hash = context.args[0].strip()
    if not payments.is_valid_tx_hash(tx_hash):
        await msg.reply_text("Invalid TX hash. Expected 64 hex characters.")
        return
    if await db.payment_is_confirmed(tx_hash):
        await msg.reply_text("This TX hash already used.")
        return
    status_msg = await msg.reply_text("🔎 Verifying USDT TRC20 payment...")
    try:
        result = await payments.verify_usdt_trc20_transaction(tx_hash, config.PAYMENT_AMOUNT_USDT)
    except Exception:
        await status_msg.edit_text("❌ Verification failed. Try again later.")
        return
    raw = json.dumps(result.raw or {}, ensure_ascii=False)
    if result.confirmed and result.amount_usdt + 1e-9 >= config.PAYMENT_AMOUNT_USDT:
        await db.record_payment(tx_hash, user.id, result.amount_usdt, "confirmed", raw)
        await db.activate_paid_subscription(user.id, tx_hash)
        await status_message.edit_text("✅ Payment verified!\nSubscription: PAID\nNotifications: unlimited")
        return
    if result.confirmed:
        await db.record_payment(tx_hash, user.id, result.amount_usdt, "underpaid", raw)
        await status_msg.edit_text(f"❌ Amount too low: {result.amount_usdt} USDT (need {config.PAYMENT_AMOUNT_USDT})")
        return
    await db.record_payment(tx_hash, user.id, 0, "failed", raw)
    await status_msg.edit_text(f"❌ Payment failed: {result.error or 'Unknown error'}")

async def unknown_command(update, context):
    msg = update.effective_message
    if msg: await msg.reply_text("Unknown command. Use /help")

async def error_handler(update, context):
    logger.error("Exception:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try: await update.effective_message.reply_text("An error occurred. Please try again.")
        except TelegramError: pass
