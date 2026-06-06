"""
Central configuration for pinepi-speaker.

Operator-editable settings are read from /etc/pinepi-speaker/config.json.
All filesystem paths are derived from BASE_DIR (code constants, not user-editable).
"""

import json
import os
import sys

# ---------------- Install-time constants ----------------

BASE_DIR = "/opt/pinepi-speaker"

PIPER_DIR = os.path.join(BASE_DIR, "piper")
PIPER_BIN = os.path.join(PIPER_DIR, "piper")
PIPER_SAY_SH = os.path.join(PIPER_DIR, "say.sh")
PIPER_MODEL = os.path.join(PIPER_DIR, "models", "en_US-amy-medium.onnx")
PIPER_WAV = os.path.join(PIPER_DIR, "notify.wav")

DATA_DIR = os.path.join(BASE_DIR, "data")
MESSAGES_FILE = os.path.join(DATA_DIR, "messages.json")

LOG_FILE = "/var/log/pinepi-speaker.log"

BEEP_WAV = "/tmp/pinepi-beep.wav"
BEEP_DONE_WAV = "/tmp/pinepi-beep-done.wav"

# ---------------- Operator config (/etc) ----------------

_CONFIG_FILE = "/etc/pinepi-speaker/config.json"

_DEFAULTS = {
    "wss_url": "wss://your-server/ws/",
    "auth_token": "",
    "device_name": "",
    "tts_backend": "piper",
    "audio_output": "alsa",
    "alsa_device": "plughw:CARD=Device,DEV=0",
    "pulse_sink": "@DEFAULT_SINK@",
    "piper_model": PIPER_MODEL,
}


def _load_config() -> dict:
    try:
        with open(_CONFIG_FILE) as f:
            data = json.load(f)
        return {**_DEFAULTS, **data}
    except FileNotFoundError:
        print(
            f"[pinepi-speaker] WARNING: {_CONFIG_FILE} not found, using defaults.",
            file=sys.stderr,
        )
        return dict(_DEFAULTS)
    except Exception as e:
        print(
            f"[pinepi-speaker] ERROR loading {_CONFIG_FILE}: {e}",
            file=sys.stderr,
        )
        return dict(_DEFAULTS)


CFG: dict = _load_config()


def wss_url() -> str:
    return CFG.get("wss_url", _DEFAULTS["wss_url"])


def auth_token() -> str:
    return CFG.get("auth_token", "")


def device_name() -> str:
    return CFG.get("device_name", "")


def default_tts_backend() -> str:
    return CFG.get("tts_backend", "piper")


def audio_output() -> str:
    return CFG.get("audio_output", "alsa")


def alsa_device() -> str:
    return CFG.get("alsa_device", "plughw:CARD=Device,DEV=0")


def pulse_sink() -> str:
    return CFG.get("pulse_sink", "@DEFAULT_SINK@")


def piper_model() -> str:
    return CFG.get("piper_model", PIPER_MODEL)
