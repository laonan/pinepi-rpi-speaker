# pinepi-speaker

A self-hosted smart speaker for Raspberry Pi. Receives push notifications from a WebSocket server, speaks them aloud via local Piper TTS, and supports USB keyboard control, scheduled voice reminders, and birthday announcements — all configurable through a single JSON file with no cloud dependency required.

## Features

- **WebSocket subscription** — receives push messages from [pinepi-broadcast-mid](https://github.com/laonan/pinepi-broadcast-mid)
- **USB keyboard control** — play / previous / next / summary / clear-read via custom wireless keyboard
- **TTS adapter layer** — local Piper for privacy-sensitive text; extensible to cloud APIs per-message
- **Scheduled reminders** — call `say.sh` directly from `sudo crontab -e`
- **systemd services** — auto-start, watchdog, journal logging

## Quick Install

```bash
git clone https://github.com/laonan/pinepi-rpi-speaker.git
cd pinepi-rpi-speaker
sudo bash install.sh
```

Then edit `/etc/pinepi-speaker/config.json`:

```json
{
  "wss_url": "wss://your-server/ws/",
  "auth_token": "YOUR_TOKEN",
  "device_name": "YOUR_DEVICE_NAME",
  "tts_backend": "piper",
  "piper_model": "/opt/pinepi-speaker/piper/models/en_US-amy-medium.onnx",
  "audio_output": "alsa",
  "alsa_device": "plughw:CARD=Device,DEV=0",
  "pulse_sink": "@DEFAULT_SINK@"
}
```

Start services:

```bash
sudo systemctl start pinepi-speaker-keyboard pinepi-speaker-ws
sudo systemctl status pinepi-speaker-keyboard pinepi-speaker-ws
```

## WebSocket Server

For the cloud WebSocket server that pushes messages to the device, deploy [pinepi-broadcast-mid](https://github.com/laonan/pinepi-broadcast-mid):

```bash
git clone https://github.com/laonan/pinepi-broadcast-mid.git
cd pinepi-broadcast-mid
# Follow the repository's README to set up the server
```

Then set `wss_url` and `auth_token` in `/etc/pinepi-speaker/config.json` to match your deployed server.

## Scheduled Reminders

Add to root's crontab (`sudo crontab -e`):

```cron
# Speak a reminder every day at 07:00
# args: <text> <model_path> <audio_output> <device>
0 7 * * * /opt/pinepi-speaker/piper/say.sh "早安，开始新的一天" /opt/pinepi-speaker/piper/models/zh_CN-huayan-medium.onnx alsa plughw:CARD=Device,DEV=0
0 7 * * * /opt/pinepi-speaker/piper/say.sh "Good morning!" /opt/pinepi-speaker/piper/models/en_US-amy-medium.onnx alsa plughw:CARD=Device,DEV=0
```

### Birthday Reminders (optional)

Edit `/opt/pinepi-speaker/data/birthdays.json` to add family birthdays (solar or lunar calendar). Then add to `sudo crontab -e`:

```cron
# Check birthdays every day at 07:00
0 7 * * * PYTHONPATH=/opt/pinepi-speaker /opt/pinepi-speaker/venv/bin/python /opt/pinepi-speaker/birthday/check_birthday.py
```

Each entry in `birthdays.json` supports:

```json
[
  { "name": "Mom", "type": "lunar", "month": 1, "day": 1, "msg": "Happy birthday Mom!" },
  { "name": "Sister", "type": "solar", "month": 6, "day": 15, "msg": "Happy birthday Sister!" }
]
```

`type` is `"solar"` (Gregorian) or `"lunar"` (Chinese lunar). The script announces on the day and the day before.

## TTS Backends

| Backend | Key | Status |
|---|---|---|
| Piper (local) | `piper` | Implemented |
| Azure (Neural TTS) | `azure` | Interface ready, implementation deferred |
| Google Cloud | `google` | Interface ready, implementation deferred |
| Alibaba Cloud | `aliyun` | Interface ready, implementation deferred |

Per-message override: add `"tts_type": "volcano"` to a message object.  
Fallback chain: **message `tts_type`** → **global `tts_backend`** → **piper**

## Layout

```
/opt/pinepi-speaker/
├── pinepi_speaker/       # Python package
│   ├── config.py         # Loads /etc/pinepi-speaker/config.json
│   ├── tts/              # Adapter layer (base, piper, registry)
│   ├── messages.py       # Shared message store
│   ├── keyboard_listener.py
│   ├── ws_client.py
│   └── remind.py
├── birthday/             # Optional birthday reminder script
│   └── check_birthday.py
├── skills/               # Hermes Agent skills (Skills Hub compatible)
│   └── sendvoice/
├── piper/                # Piper binary + models + say.sh
├── data/                 # Runtime data (preserved on reinstall)
│   ├── messages.json
│   └── birthdays.json
├── venv/                 # Python virtualenv (created by install.sh)
└── systemd/              # Service unit files

/etc/pinepi-speaker/
└── config.json           # Operator config
```

## Agent Skill

> ⚠️ **Experimental.** Tested on [Hermes Agent](https://hermes-agent.nousresearch.com) only. May also work on OpenClaw and other Skills Hub-compatible agents, but this has not been verified.

The `skills/sendvoice/` directory contains a Hermes Agent skill that lets an AI agent push voice notifications to the speaker over the WebSocket API.

### Install via Hermes Skills Hub

**Add this repo as a tap** (subscribe to all skills):
```bash
hermes skills tap add laonan/pinepi-rpi-speaker
hermes skills install laonan/pinepi-rpi-speaker/sendvoice
```

**Or install directly** (single skill, no tap needed):
```bash
hermes skills install laonan/pinepi-rpi-speaker/skills/sendvoice
```

**Or ask the agent in chat:**
> "install the sendvoice skill from laonan/pinepi-rpi-speaker"

### Setup

Set the required environment variables (in `~/.bashrc` or the Hermes systemd service):

```bash
export SENDVOICE_BEARER_TOKEN="your-api-token"
export SENDVOICE_API_URL="https://your-server/api/send"  # optional, has default
export SENDVOICE_TARGET="speaker"                        # optional, default: speaker
```

### Usage

**From a Hermes cron job or agent prompt** (recommended — inherits env vars):

```bash
/opt/hermes/.venv/bin/python3 /opt/data/skills/sendvoice/__init__.py '纯中文播报内容' 0
# arg 2: 0 = queue (wait for keypress), 1 = play immediately
```

**From Python:**

```python
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sendvoice", "/opt/data/skills/sendvoice/__init__.py")
sendvoice = importlib.util.module_from_spec(spec)
sys.modules["sendvoice"] = sendvoice
spec.loader.exec_module(sendvoice)

sendvoice.send_voice("纯中文内容")
sendvoice.send_voice("紧急通知！马上回电话", play_now=1)
```

> ⚠️ **All content must be pure Chinese.** The Piper TTS engine will spell out English letter-by-letter. Translate any English text to Chinese before calling `send_voice()`.

See `agent-skills/hermes/sendvoice/SKILL.md` for full documentation including cron job integration and Docker environment variable handling.

## License

MIT License
