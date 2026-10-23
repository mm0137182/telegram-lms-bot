FROM python:3.11-slim

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy the bot script and data files
COPY bot.py /app/bot.py
COPY lms_token.json /app/data/lms_token.json
COPY telegram_commands.json /app/data/telegram_commands.json
COPY telegram_uploads/ /app/data/telegram_uploads/
COPY .hermes/ /app/data/.hermes/

# Create data directories
RUN mkdir -p /app/data/telegram_uploads

# Set data directory (the bot uses BOT_DATA_DIR env var, defaults to /app/data)
ENV BOT_DATA_DIR=/app/data

# Run the bot in daemon mode (continuous loop, 24/7)
CMD ["python3", "bot.py"]
