import logging
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
import config
from bot import admin, db, handlers, monitoring

logger = logging.getLogger(__name__)

async def post_init(application):
    await db.init_db()
    scheduler = AsyncIOScheduler(timezone=config.TIMEZONE, job_defaults={"coalesce": True, "max_instances": 1})
    scheduler.add_job(monitoring.monitoring_cycle, trigger="interval", seconds=config.MONITOR_INTERVAL_SECONDS,
        kwargs={"application": application}, id="monitoring_cycle",
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=5))
    scheduler.start()
    application.bot_data["scheduler"] = scheduler
    logger.info("Scheduler started. Monitoring every %s seconds.", config.MONITOR_INTERVAL_SECONDS)

async def post_shutdown(application):
    scheduler = application.bot_data.get("scheduler")
    if scheduler: scheduler.shutdown(wait=False)

def build_application():
    config.validate_config()
    app = Application.builder().token(config.BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()
    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("help", handlers.help_command))
    app.add_handler(CommandHandler("subscribe", handlers.subscribe))
    app.add_handler(CommandHandler("notify", handlers.notify))
    app.add_handler(CommandHandler("keywords", handlers.keywords))
    app.add_handler(CommandHandler("remove", handlers.remove))
    app.add_handler(CommandHandler("upgrade", handlers.upgrade))
    app.add_handler(CommandHandler("stats", admin.stats))
    app.add_handler(CommandHandler("broadcast", admin.broadcast))
    app.add_handler(MessageHandler(filters.COMMAND, handlers.unknown_command))
    app.add_error_handler(handlers.error_handler)
    return app

def main():
    logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=config.LOG_LEVEL)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    application = build_application()
    logger.info("Starting smart-notify-bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
