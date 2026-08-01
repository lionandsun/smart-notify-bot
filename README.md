# smart-notify-bot

Production-ready Telegram bot with keyword monitoring, subscriptions, admin tools, SQLite storage, APScheduler background jobs, and mock USDT TRC20 payment verification.

## Features

- `/start` — welcome message
- `/subscribe` — subscription status
- `/notify <keyword>` — add keyword monitoring
- `/keywords` — list active keywords
- `/remove <id>` — remove keyword
- `/upgrade <tx_hash>` — USDT TRC20 payment verification
- `/stats` — admin: bot statistics
- `/broadcast` — admin: send message to all users
- Free tier: 5 notifications/day
- Paid tier: unlimited notifications

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your BOT_TOKEN and ADMIN_USER_IDS
python main.py
```

## License

MIT
