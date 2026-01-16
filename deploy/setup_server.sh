#!/bin/bash
# Initial server setup for Spanish Translator bot

set -e

SERVER="root@178.156.209.222"

echo "Setting up Spanish Translator on Hetzner..."

ssh $SERVER << 'EOF'
# Update system
apt update && apt upgrade -y

# Install Python
apt install -y python3 python3-pip python3-venv

# Create directories
mkdir -p /opt/spanish-translator/data
mkdir -p /opt/spanish-translator/telegram_bot

echo "Server setup complete!"
echo "Now run deploy.sh and create .env file on server"
EOF

echo ""
echo "Next steps:"
echo "1. Create .env file on server: ssh $SERVER 'nano /opt/spanish-translator/telegram_bot/.env'"
echo "2. Run deploy.sh"
