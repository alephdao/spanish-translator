#!/usr/bin/env python3
"""
Spanish Translator Telegram Bot - Using Claude Agent SDK
Translates messages to Argentine Spanish using Claude.
"""

from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message
from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    TextBlock,
)

from modules import transcribe_audio, ConversationManager

# Configuration
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
LOCAL_MODE = os.getenv("LOCAL_MODE", "false").lower() == "true"
HETZNER_HOST = os.getenv("HETZNER_HOST", "178.156.209.222")
HETZNER_USER = os.getenv("HETZNER_USER", "root")
HETZNER_DATA_DIR = os.getenv("HETZNER_DATA_DIR", "/opt/spanish-translator/data")
LOCAL_DATA_DIR = os.getenv("LOCAL_DATA_DIR", str(Path(__file__).parent / "data"))
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20241022")

PROJECT_ROOT = Path(__file__).parent.parent
PROMPTS_DIR = Path(__file__).parent / "prompts"

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Per-user Claude clients
claude_clients: dict[int, ClaudeSDKClient] = {}

# Conversation manager (initialized in main)
conversation_manager: Optional[ConversationManager] = None


def load_system_prompt() -> str:
    """Load system prompt from prompts/system_prompt.md"""
    prompt_path = PROMPTS_DIR / "system_prompt.md"
    if not prompt_path.exists():
        logger.warning(f"Prompt file not found: {prompt_path}")
        return "You are an Argentine Spanish translator. Translate the input to Argentine Spanish (castellano rioplatense). Return only the translation, nothing else."
    with open(prompt_path, 'r') as f:
        return f.read()


async def initialize_claude_client() -> ClaudeSDKClient:
    """Initialize Claude SDK client with custom system prompt"""
    system_prompt = load_system_prompt()

    options = ClaudeAgentOptions(
        cwd=str(PROJECT_ROOT),
        system_prompt=system_prompt,
        model=CLAUDE_MODEL,
        permission_mode="bypassPermissions",
        max_turns=5,
    )

    client = ClaudeSDKClient(options=options)
    await client.__aenter__()
    return client


async def get_client_for_user(user_id: int) -> ClaudeSDKClient:
    """Get or create Claude client for a specific user"""
    if user_id not in claude_clients:
        logger.info(f"Creating new Claude client for user {user_id}")
        claude_clients[user_id] = await initialize_claude_client()
    return claude_clients[user_id]


async def reset_client_for_user(user_id: int):
    """Reset Claude client for a user (starts fresh conversation)"""
    if user_id in claude_clients:
        logger.info(f"Resetting Claude client for user {user_id}")
        try:
            await claude_clients[user_id].__aexit__(None, None, None)
        except Exception as e:
            logger.warning(f"Error closing client for user {user_id}: {e}")
        del claude_clients[user_id]


async def translate_message(user_id: int, text: str) -> str:
    """Translate a message to Argentine Spanish using Claude SDK"""
    client = await get_client_for_user(user_id)

    # Get conversation history for context
    history = conversation_manager.get_messages(user_id)

    # Build context from history
    context_parts = []
    for msg in history[-6:]:  # Last 6 messages for context
        role = "User" if msg["role"] == "user" else "Translation"
        context_parts.append(f"{role}: {msg['content']}")

    if context_parts:
        full_prompt = f"Previous translations:\n{chr(10).join(context_parts)}\n\nNow translate this: {text}"
    else:
        full_prompt = f"Translate this to Argentine Spanish: {text}"

    # Save user message
    conversation_manager.add_message(user_id, "user", text)

    # Query Claude
    await client.query(full_prompt)

    # Get response
    response_text = ""
    async for sdk_message in client.receive_response():
        if isinstance(sdk_message, AssistantMessage):
            for block in sdk_message.content:
                if isinstance(block, TextBlock):
                    response_text += block.text

    if not response_text:
        response_text = "Error: No pude generar la traduccion."

    # Save translation
    conversation_manager.add_message(user_id, "assistant", response_text)

    return response_text


async def main():
    """Main function"""
    global conversation_manager

    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN not found!")
        return

    # Initialize conversation manager
    if LOCAL_MODE:
        conversation_manager = ConversationManager(
            data_dir=LOCAL_DATA_DIR,
            local_mode=True
        )
        logger.info(f"Conversation manager initialized (LOCAL: {LOCAL_DATA_DIR})")
    else:
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
            "Send me any text or voice message and I'll translate it to Argentine Spanish (castellano rioplatense).\n\n"
            "Commands:\n"
            "- /new - Start a new conversation\n"
            "- /history - Show recent translations"
        )

    @dp.message(F.text.startswith("/new"))
    async def cmd_new(message: Message):
        user_id = message.from_user.id
        new_conv_id = conversation_manager.new_conversation(user_id)
        await reset_client_for_user(user_id)
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
        # Cleanup all per-user Claude clients
        for user_id, client in list(claude_clients.items()):
            try:
                await client.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error closing client for user {user_id}: {e}")
        claude_clients.clear()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
