# Spanish Translator

A Telegram bot that translates messages to Argentine Spanish (castellano rioplatense).

## Architecture

- **Frontend**: Telegram bot (aiogram)
- **Backend**: Anthropic Claude API (claude-haiku)
- **Storage**: JSON files on Hetzner server (via SSH)
- **Voice**: Google Gemini for transcription

## Key Files
- `telegram_bot/bot.py` - Main bot
- `telegram_bot/modules/conversation.py` - JSON storage on Hetzner
- `telegram_bot/prompts/system_prompt.md` - Translation instructions

## Hetzner Server
- **IP**: 178.156.209.222
- **SSH**: `ssh root@178.156.209.222`
- **Data**: `/opt/spanish-translator/data/` (JSON files)
- **Service**: `systemctl status spanish-translator-bot`

## Commands
```bash
# Deploy
./deploy/deploy.sh

# View logs
ssh root@178.156.209.222 'journalctl -u spanish-translator-bot -f'

# Restart
ssh root@178.156.209.222 'systemctl restart spanish-translator-bot'
```

## Telegram Commands
- `/start` - Show help
- `/new` - Start new conversation
- `/history` - Show recent translations
