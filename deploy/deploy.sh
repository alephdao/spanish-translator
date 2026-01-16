#!/bin/bash
# Deploy Spanish Translator bot to Hetzner

set -e

SERVER="root@178.156.209.222"
REMOTE_DIR="/opt/spanish-translator"

echo "Deploying Spanish Translator to Hetzner..."

# Create directories on server
ssh $SERVER "mkdir -p $REMOTE_DIR/data"

# Sync files (excluding .env and __pycache__)
rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude '.env' --exclude '*.pyc' \
    ../telegram_bot/ $SERVER:$REMOTE_DIR/telegram_bot/

# Setup on server
ssh $SERVER << 'EOF'
cd /opt/spanish-translator

# Create venv if not exists
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

# Install dependencies
source .venv/bin/activate
pip install -r telegram_bot/requirements.txt

# Create systemd service
cat > /etc/systemd/system/spanish-translator-bot.service << 'SERVICE'
[Unit]
Description=Spanish Translator Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/spanish-translator
Environment=PATH=/opt/spanish-translator/.venv/bin
EnvironmentFile=/opt/spanish-translator/telegram_bot/.env
ExecStart=/opt/spanish-translator/.venv/bin/python telegram_bot/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE

# Reload and restart service
systemctl daemon-reload
systemctl enable spanish-translator-bot
systemctl restart spanish-translator-bot

echo "Service status:"
systemctl status spanish-translator-bot --no-pager
EOF

echo "Deployment complete!"
echo ""
echo "Commands:"
echo "  View logs: ssh $SERVER 'journalctl -u spanish-translator-bot -f'"
echo "  Restart:   ssh $SERVER 'systemctl restart spanish-translator-bot'"
echo "  Status:    ssh $SERVER 'systemctl status spanish-translator-bot'"
