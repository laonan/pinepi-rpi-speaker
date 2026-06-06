#!/bin/bash
# Usage: say.sh <text> [model_path] [audio_output] [device]
#   audio_output: alsa | pulse   (default: from config.json, fallback alsa)
#   device:       alsa → plughw:... string   pulse → sink name or @DEFAULT_SINK@

set -euo pipefail

TEXT="$1"
BASE_DIR="/opt/pinepi-speaker/piper"
CFG="/etc/pinepi-speaker/config.json"
FILE="${BASE_DIR}/notify.wav"

# --- read config.json defaults (requires jq) ---
_cfg() { jq -r --arg k "$1" --arg d "$2" 'if has($k) and .[$k] != "" then .[$k] else $d end' "$CFG" 2>/dev/null || echo "$2"; }

if [[ -f "$CFG" ]] && command -v jq &>/dev/null; then
    DEFAULT_MODEL=$(_cfg "piper_model" "${BASE_DIR}/models/en_US-amy-medium.onnx")
    DEFAULT_OUTPUT=$(_cfg "audio_output" "alsa")
    DEFAULT_ALSA=$(_cfg "alsa_device"   "plughw:CARD=Device,DEV=0")
    DEFAULT_PULSE=$(_cfg "pulse_sink"   "@DEFAULT_SINK@")
else
    DEFAULT_MODEL="${BASE_DIR}/models/en_US-amy-medium.onnx"
    DEFAULT_OUTPUT="alsa"
    DEFAULT_ALSA="plughw:CARD=Device,DEV=0"
    DEFAULT_PULSE="@DEFAULT_SINK@"
fi

MODEL="${2:-$DEFAULT_MODEL}"
AUDIO_OUTPUT="${3:-$DEFAULT_OUTPUT}"
DEVICE="${4:-}"

# --- synthesise ---
echo "$TEXT" | "${BASE_DIR}/piper" --model "$MODEL" -f "$FILE"

# --- play ---
case "$AUDIO_OUTPUT" in
    pulse)
        SINK="${DEVICE:-$DEFAULT_PULSE}"
        paplay --device="$SINK" "$FILE"
        ;;
    alsa|*)
        ALSA_DEV="${DEVICE:-$DEFAULT_ALSA}"
        aplay -D "$ALSA_DEV" "$FILE"
        ;;
esac
