#!/bin/bash
# Start Telegram LMS Bot as a background process (24/7)
# This runs the Python bot directly — no Docker required

cd "$(dirname "$0")"

# Create data directory
mkdir -p /app/data/telegram_uploads /app/data/.hermes/secrets

# Initialize commands file if not exists
if [ ! -f "/app/data/telegram_commands.json" ]; then
    echo '{"last_update_id": 0, "pending": [], "processed": [], "uploads": []}' > /app/data/telegram_commands.json
fi

# Copy token and config if they exist in current dir
[ -f "lms_token.json" ] && cp lms_token.json /app/data/lms_token.json
[ -f ".hermes/secrets/telegram_config.json" ] && cp .hermes/secrets/telegram_config.json /app/data/.hermes/secrets/telegram_config.json

# Run bot in background with nohup, restart on failure
echo "🚀 Starting Telegram LMS Bot (24/7 mode)..."
while true; do
    BOT_DATA_DIR=/app/data python3 /app/bot.py 2>&1
    echo "[$(date '+%H:%M:%S')] Bot exited — restarting in 5 seconds..."
    sleep 5
done
