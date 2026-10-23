#!/bin/bash
# Telegram → Hermes Bot Deployment Script
# Deploys the bot to a 24/7 server using Docker

set -e

echo "🚀 Setting up Telegram LMS Bot..."
echo "===================================="

# Ensure we're in the deploy directory
cd "$(dirname "$0")"

echo "📋 Checking prerequisites..."

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Install from: https://docs.docker.com/get-docker/"
    exit 1
fi
echo "✓ Docker: $(docker --version)"

# Check Docker Compose
if ! docker compose version &> /dev/null 2>&1; then
    if ! docker-compose version &> /dev/null 2>&1; then
        echo "❌ Docker Compose not found. Install from: https://docs.docker.com/compose/install/"
        exit 1
    fi
    COMPOSE_CMD="docker-compose"
else
    COMPOSE_CMD="docker compose"
fi
echo "✓ Docker Compose available"

# Create data directory if it doesn't exist
mkdir -p data/telegram_uploads data/.hermes/secrets

# Check if config files exist
if [ ! -f "data/lms_token.json" ]; then
    echo "⚠️  No LMS token found. The bot needs lms_token.json in data/"
    echo "   Copy your token file: cp /path/to/lms_token.json data/lms_token.json"
fi

if [ ! -f "data/telegram_commands.json" ]; then
    # Initialize with empty state
    echo '{"last_update_id": 0, "pending": [], "processed": [], "uploads": []}' > data/telegram_commands.json
    echo "✓ Initialized telegram_commands.json"
fi

# Build and start the container
echo ""
echo "🐳 Building Docker image..."
$COMPOSE_CMD build

echo ""
echo "🏃 Starting bot container (24/7 daemon mode)..."
$COMPOSE_CMD up -d

echo ""
echo "✅ Bot deployed successfully!"
echo ""
echo "📊 Status:"
$COMPOSE_CMD ps
echo ""
echo "📋 Logs:"
echo "  docker compose logs -f telegram-bot"
echo ""
echo "🛑 Stop:"
echo "  docker compose down"
echo ""
echo "The bot will now poll Telegram every second for new messages."
echo "To deploy to a cloud server (Railway/Render/DigitalOcean):"
echo "  1. Push this directory to a git repo"
echo "  2. Connect to Railway.app or Render.com"
echo "  3. Or run on any VPS with Docker installed"
