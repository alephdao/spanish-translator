"""
Conversation manager using JSON files stored on Hetzner server.
Uses SSH/SCP to read and write conversation data.
"""

import json
import logging
import subprocess
import uuid
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class ConversationManager:
    """Manages conversation history as JSON files on Hetzner server."""

    def __init__(self, hetzner_host: str, hetzner_user: str, data_dir: str):
        self.hetzner_host = hetzner_host
        self.hetzner_user = hetzner_user
        self.data_dir = data_dir
        self.ssh_target = f"{hetzner_user}@{hetzner_host}"

        # Local cache of current conversation IDs per user
        self._current_conv: dict[int, str] = {}

        # Ensure data directory exists on server
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
        """Ensure data directory exists on server."""
        success, _ = self._run_ssh(f"mkdir -p {self.data_dir}")
        if not success:
            logger.warning(f"Could not create data dir: {self.data_dir}")

    def _get_user_file(self, user_id: int) -> str:
        """Get path to user's conversation file on server."""
        return f"{self.data_dir}/user_{user_id}.json"

    def _read_user_data(self, user_id: int) -> dict:
        """Read user's conversation data from server."""
        remote_file = self._get_user_file(user_id)
        success, output = self._run_ssh(f"cat {remote_file} 2>/dev/null || echo '{{}}'")

        if success and output:
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON for user {user_id}, starting fresh")
                return {}
        return {}

    def _write_user_data(self, user_id: int, data: dict):
        """Write user's conversation data to server."""
        remote_file = self._get_user_file(user_id)
        json_str = json.dumps(data, indent=2, ensure_ascii=False)

        # Escape for bash
        escaped = json_str.replace("'", "'\"'\"'")

        success, _ = self._run_ssh(f"echo '{escaped}' > {remote_file}")
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
