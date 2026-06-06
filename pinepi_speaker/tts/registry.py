"""TTS adapter registry and resolution.

Resolution order for resolve_adapter(tts_type):
  1. tts_type argument (per-message override) — if registered
  2. global default from config.json (tts_backend field) — if registered
  3. PiperAdapter hard fallback (always available)
"""

import logging
from typing import Optional

from pinepi_speaker import config
from pinepi_speaker.tts.base import TTSAdapter
from pinepi_speaker.tts.piper_adapter import PiperAdapter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Registry: maps backend name → adapter class
# To add a new cloud backend, import its class and add one entry here.
# ---------------------------------------------------------------------------

REGISTRY: dict[str, type[TTSAdapter]] = {
    "piper": PiperAdapter,
    # "volcano": VolcanoAdapter,   # future
    # "aliyun":  AliyunAdapter,    # future
}

# Module-level singleton instances (lazy-initialised, shared across daemons)
_instances: dict[str, TTSAdapter] = {}


def _get_or_create(name: str) -> TTSAdapter:
    if name not in _instances:
        cls = REGISTRY[name]
        instance = cls()
        if hasattr(instance, "start"):
            instance.start()
        _instances[name] = instance
    return _instances[name]


def resolve_adapter(tts_type: Optional[str]) -> TTSAdapter:
    """Return the best available TTSAdapter for *tts_type*.

    Falls back gracefully:
      message tts_type → global default → piper
    """
    candidates = []

    if tts_type:
        candidates.append(tts_type.strip().lower())

    global_default = config.default_tts_backend()
    if global_default:
        candidates.append(global_default.strip().lower())

    candidates.append("piper")

    seen = []
    for name in candidates:
        if name in seen:
            continue
        seen.append(name)
        if name not in REGISTRY:
            if name not in ("piper",):
                logger.warning("TTS backend '%s' is not registered, skipping", name)
            continue
        try:
            return _get_or_create(name)
        except Exception as e:
            logger.warning("Failed to initialise TTS adapter '%s': %s", name, e)

    logger.error("All TTS adapters failed; bare PiperAdapter created as last resort")
    instance = PiperAdapter()
    instance.start()
    return instance
