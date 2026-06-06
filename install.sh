#!/bin/bash
# pinepi-speaker installer
# Installs to /opt/pinepi-speaker and registers two systemd services.
# Safe to re-run (idempotent).

set -euo pipefail

INSTALL_DIR="/opt/pinepi-speaker"
VENV_DIR="${INSTALL_DIR}/venv"
ETC_DIR="/etc/pinepi-speaker"
SYSTEMD_DIR="/etc/systemd/system"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

# ---- must run as root ----
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: run as root (sudo ./install.sh)" >&2
    exit 1
fi

# ---- piper model selector ----

_select_model() {
    local models_dir="${INSTALL_DIR}/piper/models"
    local -a model_files
    local idx=0

    while IFS= read -r -d '' f; do
        model_files[$idx]="$f"
        idx=$((idx+1))
    done < <(find "$models_dir" -maxdepth 1 -name '*.onnx' -print0 2>/dev/null | sort -z)

    if [[ $idx -eq 0 ]]; then
        echo "    WARNING: No .onnx models found in ${models_dir}" >&2
        PIPER_MODEL="${models_dir}/en_US-amy-medium.onnx"
        return
    fi

    if [[ $idx -eq 1 ]]; then
        PIPER_MODEL="${model_files[0]}"
        echo "    Auto-selected model: $(basename "$PIPER_MODEL")"
        return
    fi

    echo ""
    echo "Available Piper TTS models:"
    for ((i=0; i<idx; i++)); do
        echo "  $((i+1))) $(basename "${model_files[$i]}")"
    done
    echo ""
    while true; do
        read -rp "Select model [1-${idx}]: " choice
        if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= idx )); then
            PIPER_MODEL="${model_files[$((choice-1))]}"
            echo "    Selected: $(basename "$PIPER_MODEL")"
            return
        fi
        echo "    Invalid choice, try again."
    done
}

# ---- speaker detection helpers ----

_detect_alsa_speakers() {
    aplay -l 2>/dev/null | awk '
        /^card [0-9]+:.*device [0-9]+:/ {
            match($0, /card [0-9]+: ([^[,]+)/, cname)
            match($0, /device ([0-9]+):/, dnum)
            cardname=cname[1]; gsub(/[[:space:]]+$/, "", cardname)
            devnum=dnum[1]
            printf "alsa|plughw:CARD=%s,DEV=%s|%s (ALSA)\n", cardname, devnum, cardname
        }
    ' | sort -u
}

_detect_pulse_sinks() {
    if command -v pactl &>/dev/null && pactl info &>/dev/null 2>&1; then
        pactl list short sinks 2>/dev/null | awk '{
            sink=$2
            if (sink ~ /bluez/) label="Bluetooth"
            else label="PulseAudio"
            printf "pulse|%s|%s (%s)\n", sink, sink, label
        }'
    fi
}

_select_speaker() {
    local -a types labels devices
    local idx=0

    while IFS='|' read -r type device label; do
        types[$idx]="$type"
        devices[$idx]="$device"
        labels[$idx]="$label"
        idx=$((idx+1))
    done < <({ _detect_alsa_speakers; _detect_pulse_sinks; } | sort -u)

    if [[ $idx -eq 0 ]]; then
        echo "    WARNING: No audio devices detected, using built-in defaults" >&2
        SPEAKER_OUTPUT="alsa"
        SPEAKER_DEVICE="plughw:CARD=Device,DEV=0"
        return
    fi

    if [[ $idx -eq 1 ]]; then
        echo "    Auto-selected: ${labels[0]}"
        SPEAKER_OUTPUT="${types[0]}"
        SPEAKER_DEVICE="${devices[0]}"
        return
    fi

    echo ""
    echo "Multiple audio devices detected. Select one:"
    for ((i=0; i<idx; i++)); do
        echo "  $((i+1))) ${labels[$i]}"
    done
    echo ""
    while true; do
        read -rp "Enter number [1-${idx}]: " choice
        if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= idx )); then
            local sel=$((choice-1))
            SPEAKER_OUTPUT="${types[$sel]}"
            SPEAKER_DEVICE="${devices[$sel]}"
            echo "    Selected: ${labels[$sel]}"
            return
        fi
        echo "    Invalid choice, try again."
    done
}

echo "==> Installing pinepi-speaker to ${INSTALL_DIR}"

# 1. Copy source tree
mkdir -p "${INSTALL_DIR}"
rsync -a --delete \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.DS_Store' \
    --exclude='venv/' \
    --exclude='data/' \
    "${REPO_DIR}/" "${INSTALL_DIR}/"

# 2. Create data directory (preserve existing data files)
mkdir -p "${INSTALL_DIR}/data"
if [[ ! -f "${INSTALL_DIR}/data/birthdays.json" ]]; then
    cp "${REPO_DIR}/data/birthdays.json" "${INSTALL_DIR}/data/birthdays.json"
fi

# 3. Make say.sh executable
chmod +x "${INSTALL_DIR}/piper/say.sh"

# 4. Ensure build dependencies are present
echo "==> Installing system build dependencies"
apt-get update -qq
if ! apt-get install -y --no-install-recommends python3-venv python3-dev jq; then
    echo ""
    echo "ERROR: Failed to install python3-dev. Try fixing apt first:" >&2
    echo "  sudo apt --fix-broken install" >&2
    echo "  sudo apt-get update && sudo apt-get install -y python3-dev" >&2
    exit 1
fi

# 5. Create virtualenv and install Python dependencies
echo "==> Setting up Python virtualenv at ${VENV_DIR}"
if [[ ! -f "${VENV_DIR}/bin/python" ]]; then
    python3 -m venv "${VENV_DIR}"
fi
echo "==> Installing Python dependencies"
"${VENV_DIR}/bin/pip" install --quiet -r "${INSTALL_DIR}/requirements.txt"
echo "${INSTALL_DIR}" > "${VENV_DIR}/lib/$(ls "${VENV_DIR}/lib")/site-packages/pinepi_speaker.pth"

# 6. Piper model selection
echo "==> Selecting Piper TTS model"
PIPER_MODEL=""
if [[ -f "${ETC_DIR}/config.json" ]]; then
    EXISTING_MODEL=$(jq -r '.piper_model // ""' "${ETC_DIR}/config.json" 2>/dev/null || echo "")
    if [[ -n "$EXISTING_MODEL" && -f "$EXISTING_MODEL" ]]; then
        echo "    Existing model: $(basename "$EXISTING_MODEL")"
        echo ""
        echo "  1) Keep existing model"
        echo "  2) Select a different model"
        echo ""
        read -rp "Choice [1/2, default 1]: " remodel
        if [[ "$remodel" == "2" ]]; then
            _select_model
        else
            PIPER_MODEL="$EXISTING_MODEL"
            echo "    Keeping existing model"
        fi
    else
        _select_model
    fi
else
    _select_model
fi

# 7. Speaker detection and config.json setup
echo "==> Detecting audio devices"
mkdir -p "${ETC_DIR}"

SPEAKER_OUTPUT="alsa"
SPEAKER_DEVICE="plughw:CARD=Device,DEV=0"

if [[ -f "${ETC_DIR}/config.json" ]]; then
    EXISTING_OUTPUT=$(jq -r '.audio_output // ""' "${ETC_DIR}/config.json" 2>/dev/null || echo "")
    EXISTING_DEVICE=$(jq -r '.alsa_device // .pulse_sink // ""' "${ETC_DIR}/config.json" 2>/dev/null || echo "")
    if [[ -n "$EXISTING_OUTPUT" && -n "$EXISTING_DEVICE" ]]; then
        echo "    Existing audio config: output=${EXISTING_OUTPUT}, device=${EXISTING_DEVICE}"
        echo ""
        echo "  1) Keep existing configuration"
        echo "  2) Detect and select a new device"
        echo ""
        read -rp "Choice [1/2, default 1]: " reconfigure
        if [[ "$reconfigure" == "2" ]]; then
            _select_speaker
        else
            echo "    Keeping existing audio configuration"
            SPEAKER_OUTPUT="$EXISTING_OUTPUT"
            SPEAKER_DEVICE="$EXISTING_DEVICE"
        fi
    else
        _select_speaker
    fi
else
    _select_speaker
fi

# Build pulse_sink / alsa_device fields
if [[ "$SPEAKER_OUTPUT" == "pulse" ]]; then
    AUDIO_FIELD_KEY="pulse_sink"
else
    AUDIO_FIELD_KEY="alsa_device"
fi

if [[ ! -f "${ETC_DIR}/config.json" ]]; then
    echo "==> Creating ${ETC_DIR}/config.json"
    cat > "${ETC_DIR}/config.json" << ENDJSON
{
  "wss_url": "wss://your-server/ws/",
  "auth_token": "",
  "device_name": "",
  "tts_backend": "piper",
  "piper_model": "${PIPER_MODEL}",
  "audio_output": "${SPEAKER_OUTPUT}",
  "${AUDIO_FIELD_KEY}": "${SPEAKER_DEVICE}"
}
ENDJSON
    echo "    !! Edit ${ETC_DIR}/config.json and fill in auth_token + device_name before starting services."
else
    # Patch model + audio fields into existing config using jq (preserve other fields)
    TMPFILE=$(mktemp)
    MODEL_PATCH=""
    [[ -n "$PIPER_MODEL" ]] && MODEL_PATCH="| .piper_model=\$model"
    jq --arg model "$PIPER_MODEL" \
       --arg out "$SPEAKER_OUTPUT" \
       --arg key "$AUDIO_FIELD_KEY" \
       --arg dev "$SPEAKER_DEVICE" \
        ".audio_output=\$out | .[\$key]=\$dev ${MODEL_PATCH}" "${ETC_DIR}/config.json" > "$TMPFILE" \
        && mv "$TMPFILE" "${ETC_DIR}/config.json"
    echo "==> Updated audio/model config in ${ETC_DIR}/config.json"
fi

# 8. Install and enable systemd services
echo "==> Installing systemd services"
for svc in pinepi-speaker-keyboard pinepi-speaker-ws; do
    cp "${INSTALL_DIR}/systemd/${svc}.service" "${SYSTEMD_DIR}/${svc}.service"
done

systemctl daemon-reload

for svc in pinepi-speaker-keyboard pinepi-speaker-ws; do
    systemctl enable "${svc}.service"
    echo "    enabled ${svc}.service"
done

echo ""
echo "==> Installation complete."
echo ""
echo "Next steps:"
echo "  1. Edit ${ETC_DIR}/config.json  (set auth_token and device_name)"
echo "  2. sudo systemctl start pinepi-speaker-keyboard pinepi-speaker-ws"
echo "  3. sudo systemctl status pinepi-speaker-keyboard pinepi-speaker-ws"
echo ""
echo "Crontab reminder example (crontab -e):"
echo "  0 7 * * * ${INSTALL_DIR}/piper/say.sh \"morning reminder text\""
