# Telegram LMS Bot

Telegram → Hermes Bot integration that polls for messages and handles LMS file uploads via the IbnRoshd platform.

## Deploy to Railway (24/7)

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template)

### Steps:
1. Push to GitHub
2. Create Railway project → "Deploy from GitHub"
3. Set `BOT_DATA_DIR=/app/data` env var
4. Deploy!

## Run directly (no Docker)

```bash
pip install -r requirements.txt  # None needed — uses only Python stdlib
python3 bot.py
```

## What the bot does

- Polls Telegram every 1s for new messages
- Receives files from Telegram → downloads → saves locally
- Attempts LMS upload to `apicore.ibnroshd.edu.sa/api/Common/UploadFiles`
- Sends success/failure notifications back to Telegram

## Commands

| Command | Action |
|---------|--------|
| افتح المنصة | Check LMS availability |
| رفع ملحف | Upload file to LMS |
| تحقق من الحالة | Check server status |
