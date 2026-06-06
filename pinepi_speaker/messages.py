"""Shared message store — load, save, rotate, and add messages.

All daemons (keyboard listener, ws_client) import from here.
The store lives at config.MESSAGES_FILE (under /opt/pinepi-speaker/data/).
"""

import json
import logging
import os
import time
from typing import Optional

from pinepi_speaker import config

logger = logging.getLogger(__name__)


def load_messages() -> dict:
    with open(config.MESSAGES_FILE) as f:
        return json.load(f)


def save_messages(data: dict) -> None:
    tmp = config.MESSAGES_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, config.MESSAGES_FILE)


def rotate_if_new_day() -> None:
    """If the date in messages.json is not today, archive it and create a fresh file."""
    today = time.strftime("%Y-%m-%d")
    if not os.path.exists(config.MESSAGES_FILE):
        os.makedirs(config.DATA_DIR, exist_ok=True)
        save_messages({"date": today, "current": 0, "messages": []})
        return
    data = load_messages()
    file_date = data.get("date", "")
    if file_date == today:
        return
    archive_name = os.path.join(
        config.DATA_DIR, f"messages_{file_date}.json"
    )
    os.rename(config.MESSAGES_FILE, archive_name)
    logger.info("Archived old messages to %s", archive_name)
    save_messages({"date": today, "current": 0, "messages": []})


def get_next_id(data: dict) -> int:
    if not data["messages"]:
        return 1
    return max(m["id"] for m in data["messages"]) + 1


def get_index(data: dict, cur_id: int) -> Optional[int]:
    for i, m in enumerate(data["messages"]):
        if m["id"] == cur_id:
            return i
    return None


def has_messages(data: dict) -> bool:
    return len(data["messages"]) > 0


def add_message(title: str, content: str, play_now: bool = False,
                tts_type: Optional[str] = None) -> None:
    """Prepend a new message to the store.

    Args:
        title:    Message title.
        content:  Message body (spoken aloud if *play_now* is True).
        play_now: Mark as read immediately and speak via TTS.
        tts_type: Optional TTS backend override (stored on the message object).
                  When None the global default from config.json is used at
                  play-time.
    """
    rotate_if_new_day()
    data = load_messages()
    new_id = get_next_id(data)
    new_msg: dict = {
        "id": new_id,
        "title": title,
        "content": content,
        "read": 1 if play_now else 0,
    }
    if tts_type:
        new_msg["tts_type"] = tts_type
    data["messages"].insert(0, new_msg)
    data["current"] = new_id
    save_messages(data)
    logger.info(
        "Added message id=%d title='%s' play_now=%s tts_type=%s",
        new_id, title, play_now, tts_type,
    )

    if play_now:
        from pinepi_speaker.tts.registry import resolve_adapter
        resolve_adapter(tts_type).speak(content)
