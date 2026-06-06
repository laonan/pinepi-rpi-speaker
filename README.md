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
| Volcano Engine | `volcano` | Interface ready, implementation deferred |
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
├── piper/                # Piper binary + models + say.sh
├── data/                 # Runtime data (preserved on reinstall)
│   ├── messages.json
│   └── birthdays.json
├── venv/                 # Python virtualenv (created by install.sh)
└── systemd/              # Service unit files

/etc/pinepi-speaker/
└── config.json           # Operator config
```

## License

MIT License
