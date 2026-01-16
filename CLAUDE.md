# Spanish Translator

A Telegram bot that translates messages to Argentine Spanish (castellano rioplatense).

## Architecture

- **Frontend**: Telegram bot (aiogram)
- **Backend**: Anthropic Claude API (Sonnet 4.5 default)
- **Storage**: JSON files (local or Hetzner via SSH)
- **Voice**: Google Gemini for transcription

## Key Files
- `telegram_bot/bot.py` - Main bot
- `telegram_bot/modules/conversation.py` - JSON storage (local or remote)
- `telegram_bot/prompts/system_prompt.md` - Translation instructions

## Running Locally
```bash
cd telegram_bot
pip install -r requirements.txt
# Set LOCAL_MODE=true in .env
python bot.py
```

## Hetzner Server (via Tailscale)
- **Tailscale IP**: 100.109.131.85
- **User**: admin
- **SSH**: `ssh admin@100.109.131.85`
- **Path**: `/opt/spanish-translator/`
- **Data**: `/opt/spanish-translator/data/` (JSON files)
- **Service**: `systemctl status spanish-translator-bot`

## Commands
```bash
# Deploy
ssh admin@100.109.131.85 "cd /opt/spanish-translator && sudo git pull && sudo systemctl restart spanish-translator-bot"

# View logs
ssh admin@100.109.131.85 'sudo journalctl -u spanish-translator-bot -f'

# Restart
ssh admin@100.109.131.85 'sudo systemctl restart spanish-translator-bot'
```

## Telegram Commands
- `/start` - Show help
- `/new` - Start new conversation
- `/history` - Show recent translations
