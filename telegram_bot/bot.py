#!/usr/bin/env python3
"""
Spanish Translator Telegram Bot
Translates messages to Argentine Spanish using Claude API.
Stores conversation history as JSON on Hetzner server.
"""

from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
import os
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message
import anthropic

from modules import transcribe_audio, ConversationManager

# Configuration
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
HETZNER_HOST = os.getenv("HETZNER_HOST", "178.156.209.222")
HETZNER_USER = os.getenv("HETZNER_USER", "root")
HETZNER_DATA_DIR = os.getenv("HETZNER_DATA_DIR", "/opt/spanish-translator/data")

PROJECT_ROOT = Path(__file__).parent.parent
PROMPTS_DIR = Path(__file__).parent / "prompts"

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Anthropic client
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Conversation manager (initialized in main)
conversation_manager: ConversationManager = None


def load_system_prompt() -> str:
    """Load system prompt from prompts/system_prompt.md"""
    prompt_path = PROMPTS_DIR / "system_prompt.md"
    if not prompt_path.exists():
        logger.warning(f"Prompt file not found: {prompt_path}")
        return "You are an Argentine Spanish translator. Translate the input to Argentine Spanish. Return only the translation, nothing else."
    with open(prompt_path, 'r') as f:
        return f.read()


async def translate_message(user_id: int, text: str) -> str:
    """Translate a message to Argentine Spanish using Claude"""
    system_prompt = load_system_prompt()

    # Get conversation history for context
    history = conversation_manager.get_messages(user_id)

    # Build messages array
    messages = []
    for msg in history[-10:]:  # Last 10 messages for context
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Add current message
    messages.append({"role": "user", "content": text})

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=system_prompt,
            messages=messages
        )

        # Extract text from response
        translation = ""
        for block in response.content:
            if hasattr(block, 'text'):
                translation += block.text
        translation = translation.strip()

        # Save to conversation history
        conversation_manager.add_message(user_id, "user", text)
        conversation_manager.add_message(user_id, "assistant", translation)

        return translation

    except Exception as e:
        logger.error(f"Translation error: {e}", exc_info=True)
        return f"Error translating: {str(e)}"


async def main():
    """Main function"""
    global conversation_manager

    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN not found!")
        return

    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not found!")
        return

    # Initialize conversation manager
    conversation_manager = ConversationManager(
        hetzner_host=HETZNER_HOST,
        hetzner_user=HETZNER_USER,
        data_dir=HETZNER_DATA_DIR
    )
    logger.info(f"Conversation manager initialized (Hetzner: {HETZNER_HOST})")

    # Initialize bot
    bot = Bot(token=TELEGRAM_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    @dp.message(F.text.startswith("/start"))
    async def cmd_start(message: Message):
        await message.answer(
            "Hola! I'm your Argentine Spanish translator.\n\n"
            "Send me any text or voice message and I'll translate it to Argentine Spanish.\n\n"
            "Commands:\n"
            "- /new - Start a new conversation\n"
            "- /history - Show recent translations"
        )

    @dp.message(F.text.startswith("/new"))
    async def cmd_new(message: Message):
        user_id = message.from_user.id
        new_conv_id = conversation_manager.new_conversation(user_id)
        await message.answer(f"Nueva conversacion! (ID: {new_conv_id})")

    @dp.message(F.text.startswith("/history"))
    async def cmd_history(message: Message):
        user_id = message.from_user.id
        history = conversation_manager.get_messages(user_id, limit=10)

        if not history:
            await message.answer("No hay historial todavia.")
            return

        lines = []
        for msg in history:
            role = "Tu" if msg["role"] == "user" else "Traduccion"
            content = msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"]
            lines.append(f"*{role}:* {content}")

        await message.answer("\n\n".join(lines), parse_mode="Markdown")

    @dp.message(F.voice)
    async def handle_voice(message: Message):
        """Handle voice messages - transcribe and translate"""
        user_id = message.from_user.id
        logger.info(f"Voice message from {user_id}")

        await bot.send_chat_action(message.chat.id, "typing")

        try:
            # Download voice file
            voice = message.voice
            file = await bot.get_file(voice.file_id)
            audio_data = await bot.download_file(file.file_path)
            audio_bytes = audio_data.read()

            # Transcribe
            logger.info(f"Transcribing {len(audio_bytes)} bytes...")
            transcript = await transcribe_audio(audio_bytes, "audio/ogg")
            logger.info(f"Transcript: {transcript[:100]}...")

            # Translate
            translation = await translate_message(user_id, transcript)

            # Send response with transcript
            response = f"_Transcripcion:_ {transcript}\n\n*Traduccion:* {translation}"

            MAX_LEN = 4000
            if len(response) <= MAX_LEN:
                await message.answer(response, parse_mode="Markdown")
            else:
                await message.answer(response[:MAX_LEN])

        except Exception as e:
            logger.error(f"Voice error: {e}", exc_info=True)
            await message.answer("Error procesando el audio.")

    @dp.message(F.text)
    async def handle_message(message: Message):
        """Handle text messages - translate to Argentine Spanish"""
        user_id = message.from_user.id
        text = message.text

        logger.info(f"Message from {user_id}: {text[:50]}...")

        await bot.send_chat_action(message.chat.id, "typing")

        try:
            translation = await translate_message(user_id, text)

            MAX_LEN = 4000
            if len(translation) <= MAX_LEN:
                await message.answer(translation)
            else:
                chunks = [translation[i:i+MAX_LEN] for i in range(0, len(translation), MAX_LEN)]
                for chunk in chunks:
                    await message.answer(chunk)
                    await asyncio.sleep(0.3)

            logger.info(f"Translation sent ({len(translation)} chars)")

        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            await message.answer("Error al traducir. Intenta de nuevo.")

    # Start polling
    logger.info("Starting Spanish Translator bot...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
