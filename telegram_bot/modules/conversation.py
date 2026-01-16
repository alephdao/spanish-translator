"""
Conversation manager using JSON files.
Supports both local storage and remote Hetzner server via SSH.
"""

import json
import logging
import os
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ConversationManager:
    """Manages conversation history as JSON files (local or remote)."""

    def __init__(self, hetzner_host: str = None, hetzner_user: str = None, data_dir: str = None, local_mode: bool = False):
        self.local_mode = local_mode or not hetzner_host
        self.data_dir = data_dir

        if self.local_mode:
            # Use local data directory
            if not data_dir:
                self.data_dir = str(Path(__file__).parent.parent / "data")
            logger.info(f"Using local storage: {self.data_dir}")
        else:
            self.hetzner_host = hetzner_host
            self.hetzner_user = hetzner_user
            self.ssh_target = f"{hetzner_user}@{hetzner_host}"
            logger.info(f"Using remote storage: {self.ssh_target}:{self.data_dir}")

        # Local cache of current conversation IDs per user
        self._current_conv: dict[int, str] = {}

        # Ensure data directory exists
        self._ensure_data_dir()

    def _run_ssh(self, command: str) -> tuple[bool, str]:
        """Run SSH command on Hetzner server."""
        try:
            result = subprocess.run(
                ["ssh", self.ssh_target, command],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0, result.stdout.strip()
        except subprocess.TimeoutExpired:
            logger.error(f"SSH timeout: {command}")
            return False, "Timeout"
        except Exception as e:
            logger.error(f"SSH error: {e}")
            return False, str(e)

    def _ensure_data_dir(self):
        """Ensure data directory exists."""
        if self.local_mode:
            os.makedirs(self.data_dir, exist_ok=True)
        else:
            success, _ = self._run_ssh(f"mkdir -p {self.data_dir}")
            if not success:
                logger.warning(f"Could not create data dir: {self.data_dir}")

    def _get_user_file(self, user_id: int) -> str:
        """Get path to user's conversation file on server."""
        return f"{self.data_dir}/user_{user_id}.json"

    def _read_user_data(self, user_id: int) -> dict:
        """Read user's conversation data."""
        user_file = self._get_user_file(user_id)

        if self.local_mode:
            if os.path.exists(user_file):
                try:
                    with open(user_file, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(f"Error reading {user_file}: {e}")
                    return {}
            return {}
        else:
            success, output = self._run_ssh(f"cat {user_file} 2>/dev/null || echo '{{}}'")
            if success and output:
                try:
                    return json.loads(output)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON for user {user_id}, starting fresh")
                    return {}
            return {}

    def _write_user_data(self, user_id: int, data: dict):
        """Write user's conversation data."""
        user_file = self._get_user_file(user_id)
        json_str = json.dumps(data, indent=2, ensure_ascii=False)

        if self.local_mode:
            try:
                with open(user_file, 'w', encoding='utf-8') as f:
                    f.write(json_str)
            except IOError as e:
                logger.error(f"Failed to write {user_file}: {e}")
        else:
            # Escape for bash
            escaped = json_str.replace("'", "'\"'\"'")
            success, _ = self._run_ssh(f"echo '{escaped}' > {user_file}")
            if not success:
                logger.error(f"Failed to write data for user {user_id}")

    def _get_current_conv_id(self, user_id: int) -> str:
        """Get or create current conversation ID for user."""
        if user_id in self._current_conv:
            return self._current_conv[user_id]

        # Check server for existing conversations
        data = self._read_user_data(user_id)

        if data.get("conversations"):
            # Find most recent active conversation
            convs = data["conversations"]
            active = [c for c in convs if not c.get("ended")]
            if active:
                conv_id = active[-1]["id"]
                self._current_conv[user_id] = conv_id
                return conv_id

        # Create new conversation
        return self.new_conversation(user_id)

    def new_conversation(self, user_id: int) -> str:
        """Start a new conversation for user."""
        conv_id = str(uuid.uuid4())[:8]
        self._current_conv[user_id] = conv_id

        data = self._read_user_data(user_id)

        # Mark previous conversations as ended
        if "conversations" in data:
            for conv in data["conversations"]:
                if not conv.get("ended"):
                    conv["ended"] = datetime.now().isoformat()

        # Add new conversation
        if "conversations" not in data:
            data["conversations"] = []

        data["conversations"].append({
            "id": conv_id,
            "started": datetime.now().isoformat(),
            "ended": None,
            "messages": []
        })

        self._write_user_data(user_id, data)
        logger.info(f"New conversation {conv_id} for user {user_id}")

        return conv_id

    def add_message(self, user_id: int, role: str, content: str):
        """Add a message to current conversation."""
        conv_id = self._get_current_conv_id(user_id)
        data = self._read_user_data(user_id)

        # Find conversation
        for conv in data.get("conversations", []):
            if conv["id"] == conv_id:
                conv["messages"].append({
                    "role": role,
                    "content": content,
                    "timestamp": datetime.now().isoformat()
                })
                break

        self._write_user_data(user_id, data)
        logger.debug(f"Added {role} message to conv {conv_id}")

    def get_messages(self, user_id: int, limit: Optional[int] = None) -> list[dict]:
        """Get messages from current conversation."""
        conv_id = self._get_current_conv_id(user_id)
        data = self._read_user_data(user_id)

        for conv in data.get("conversations", []):
            if conv["id"] == conv_id:
                messages = conv.get("messages", [])
                if limit:
                    return messages[-limit:]
                return messages

        return []

    def get_all_conversations(self, user_id: int) -> list[dict]:
        """Get all conversations for user (metadata only)."""
        data = self._read_user_data(user_id)
        result = []

        for conv in data.get("conversations", []):
            result.append({
                "id": conv["id"],
                "started": conv.get("started"),
                "ended": conv.get("ended"),
                "message_count": len(conv.get("messages", []))
            })

        return result
