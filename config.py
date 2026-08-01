import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

def _csv_ints(raw: str) -> list[int]:
    values = []
    for item in raw.split(","):
        item = item.strip()
        if item:
            try: values.append(int(item))
            except ValueError: pass
    return values

def _csv_strings(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]

BOT_TOKEN = os.getenv("BOT_TOKEN", "123456:ABC-REPLACE-WITH-REAL-TOKEN")
ADMIN_USER_IDS = _csv_ints(os.getenv("ADMIN_USER_IDS", ""))
DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "smart_notify_bot.sqlite3"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
TIMEZONE = os.getenv("TIMEZONE", "UTC")
FREE_DAILY_NOTIFICATION_LIMIT = int(os.getenv("FREE_DAILY_NOTIFICATION_LIMIT", "5"))
MAX_KEYWORDS_PER_USER = int(os.getenv("MAX_KEYWORDS_PER_USER", "50"))
MONITOR_INTERVAL_SECONDS = int(os.getenv("MONITOR_INTERVAL_SECONDS", "60"))
SOURCE_TYPE = os.getenv("SOURCE_TYPE", "mock").lower()
SOURCE_URL = os.getenv("SOURCE_URL", "")
PAYMENT_AMOUNT_USDT = float(os.getenv("PAYMENT_AMOUNT_USDT", "10"))
PAYMENT_WALLET_ADDRESS = os.getenv("PAYMENT_WALLET_ADDRESS", "YOUR_USDT_TRC20_WALLET_ADDRESS")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@your_support")
MOCK_MATCH_PROBABILITY = float(os.getenv("MOCK_MATCH_PROBABILITY", "0.65"))
MOCK_DEFAULT_TERMS = _csv_strings(os.getenv("MOCK_DEFAULT_TERMS", "bitcoin,ethereum,usdt,airdrop,security"))

def validate_config():
    if not BOT_TOKEN or "REPLACE-WITH-REAL-TOKEN" in BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set.")
    if SOURCE_TYPE not in {"mock", "http"}:
        raise RuntimeError("SOURCE_TYPE must be 'mock' or 'http'.")
    if SOURCE_TYPE == "http" and not SOURCE_URL:
        raise RuntimeError("SOURCE_URL must be set when SOURCE_TYPE=http.")
