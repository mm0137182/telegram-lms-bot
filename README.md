# Telegram LMS Bot — Deployment Guide

## Quick Start (Docker)

```bash
cd telegram_bot_deploy/
chmod +x deploy.sh
./deploy.sh
```

## Manual Docker Deployment

```bash
# Build the image
docker build -t telegram-lms-bot .

# Run the bot (mounts data directory for persistence)
docker run -d \
  --name telegram-lms-bot \
  --restart unless-stopped \
  -v ./data:/app/data \
  telegram-lms-bot
```

## Cloud Deployment Options

### Option 1: Railway.app (easiest)
1. Push the `telegram_bot_deploy/` directory to a GitHub repo
2. Create a Railway project → "Deploy from GitHub"
3. Select the repo, Railway auto-detects the Dockerfile
4. Set env vars: `TELEGRAM_BOT_TOKEN`, `BOT_DATA_DIR=/app/data`
5. Deploy!

### Option 2: Render.com
1. Push to GitHub
2. Create a "Web Service" on Render
3. Select Docker as environment
4. Set the start command to `python3 bot.py`
5. Deploy!

### Option 3: DigitalOcean / AWS VPS
```bash
# On the server:
git clone <your-repo>
cd telegram_bot_deploy
./deploy.sh
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BOT_DATA_DIR` | `/app/data` | Directory for config/state files |
| `TELEGRAM_BOT_TOKEN` | (from code) | Telegram bot token |

## Files Included

- `bot.py` — Main bot script (daemon mode, 24/7)
- `lms_token.json` — LMS API authentication token
- `telegram_commands.json` — Bot state (pending messages, upload queue)
- `telegram_uploads/` — Downloaded Telegram files
- `.hermes/secrets/telegram_config.json` — Hermes config

## Bot Commands

| Arabic Command | Action |
|---------------|--------|
| افتح المنصة / فتح المنصة | Check LMS availability |
| البريد الإلكتروني | Open email page |
| تحقق من الحالة | Check LMS server status |
| الحصص التفاعلية | Access class schedule |
| رفع ملف | Upload file to LMS |
| مساعدة | Show help |

## Upload Workflow

1. User sends "رفع ملف" → Bot responds "أرسل الملف الآن"
2. User sends a file → Bot downloads & saves it
3. Bot attempts upload to LMS `Common/UploadFiles`
4. Bot sends success/failure notification

## Troubleshooting

- **401 Unauthorized on GetUserInfo**: The LMS token may need refreshing. Re-login to LMS and update `lms_token.json`.
- **Res_Error on UploadFiles**: Server-side validation issue. The request format matches the Angular app exactly, but the LMS API may require additional session context.
- **Telegram API errors**: Verify `TELEGRAM_BOT_TOKEN` is correct.
