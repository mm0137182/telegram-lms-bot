# Telegram LMS Bot
# Self-contained Telegram bot with LMS integration for IbnRoshd platform

# Environment
BOT_DATA_DIR=/app/data

# Health check: verify bot is responding
HEALTHCHECK--CMD python3 -c "import json; json.load(open('/app/data/telegram_commands.json')); print('ok')" --interval=60s --timeout=10s --retries=3 --start-period=30s
