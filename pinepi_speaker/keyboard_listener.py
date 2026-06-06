#!/usr/bin/env python3
"""USB keyboard listener daemon.

Monitors a custom wireless USB keyboard and dispatches core operations:
  enter (play current), pre, next, all (summary), delread (clear read).

TTS is routed through the adapter registry — per-message tts_type field
is honoured, falling back to the global default, then to Piper.
"""

import os
import select
import signal
import socket
import sys
import threading
import time
from collections import deque

from evdev import InputDevice, ecodes, list_devices

from pinepi_speaker import config
from pinepi_speaker.messages import (
    get_index,
    has_messages,
    load_messages,
    save_messages,
)
from pinepi_speaker.tts.registry import resolve_adapter

# ---------------- Config ----------------

BUFFER_MAX_LEN = 30
DEBOUNCE_MS = 500
DELREAD_TIMEOUT = 30

BUFFER: deque = deque(maxlen=BUFFER_MAX_LEN)
LAST_ACTION_TIME = 0
PENDING_DEL_READ = False
DEL_READ_TIMESTAMP = 0.0
DEL_READ_TIMER: threading.Timer | None = None

# ---------------- Keyboard map ----------------

KEY_MAP = {
    "KEY_A": "a", "KEY_B": "b", "KEY_C": "c", "KEY_D": "d", "KEY_E": "e",
    "KEY_F": "f", "KEY_G": "g", "KEY_H": "h", "KEY_I": "i", "KEY_J": "j",
    "KEY_K": "k", "KEY_L": "l", "KEY_M": "m", "KEY_N": "n", "KEY_O": "o",
    "KEY_P": "p", "KEY_Q": "q", "KEY_R": "r", "KEY_S": "s", "KEY_T": "t",
    "KEY_U": "u", "KEY_V": "v", "KEY_W": "w", "KEY_X": "x", "KEY_Y": "y",
    "KEY_Z": "z",
    "KEY_LEFTBRACE": "[",
    "KEY_RIGHTBRACE": "]",
    "KEY_EQUAL": "=",
    "KEY_MINUS": "-",
    "KEY_1": "1", "KEY_2": "2", "KEY_3": "3", "KEY_4": "4", "KEY_5": "5",
}

# ---------------- Command aliases ----------------

COMMAND_ALIASES = {
    "enter": "enter",
    "ente":  "enter",
    "all":     "all",
    "delread": "delread",
    "pre":     "pre",
    "next":    "next",
    "=5-": "enter",
    "=1-": "all",
    "=2-": "delread",
    "=3-": "pre",
    "=4-": "next",
}

COMMAND_PATTERNS = sorted(COMMAND_ALIASES.keys(), key=len, reverse=True)

# ---------------- Logging ----------------

def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} {msg}"
    try:
        with open(config.LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)

# ---------------- systemd watchdog ----------------

def sd_notify(state: str) -> None:
    sock_path = os.environ.get("NOTIFY_SOCKET")
    if not sock_path:
        return
    try:
        if sock_path.startswith("@"):
            sock_path = "\0" + sock_path[1:]
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.connect(sock_path)
            s.sendall(state.encode())
    except Exception as e:
        log(f"sd_notify failed: {e}")


def watchdog_loop() -> None:
    sd_notify("READY=1")
    while True:
        sd_notify("WATCHDOG=1")
        time.sleep(10)

# ---------------- speak helper ----------------

def speak(text: str, tts_type: str | None = None) -> None:
    log(f"QUEUE: {text}")
    resolve_adapter(tts_type).speak(text)

# ---------------- Actions ----------------

def action_enter(data: dict) -> None:
    if not has_messages(data):
        speak("没有消息")
        return
    idx = get_index(data, data["current"])
    if idx is None:
        speak("没有消息")
        return
    msg = data["messages"][idx]
    content = msg.get("content", "")
    tts_type = msg.get("tts_type")
    data["messages"][idx]["read"] = 1
    save_messages(data)
    speak(content, tts_type)


def action_pre(data: dict) -> None:
    if not has_messages(data):
        speak("没有消息")
        return
    idx = get_index(data, data["current"])
    if idx is None or idx <= 0:
        speak("这已经是第一条了")
        return
    idx -= 1
    data["current"] = data["messages"][idx]["id"]
    save_messages(data)
    title = data["messages"][idx].get("title", "")
    read_val = data["messages"][idx].get("read", 0)
    speak(f"{title}，{'已读' if read_val == 1 else '未读'}")


def action_next(data: dict) -> None:
    if not has_messages(data):
        speak("没有消息")
        return
    idx = get_index(data, data["current"])
    if idx is None or idx >= len(data["messages"]) - 1:
        speak("这已经是最后一条了")
        return
    idx += 1
    data["current"] = data["messages"][idx]["id"]
    save_messages(data)
    title = data["messages"][idx].get("title", "")
    read_val = data["messages"][idx].get("read", 0)
    speak(f"{title}，{'已读' if read_val == 1 else '未读'}")


def action_all(data: dict) -> None:
    if not has_messages(data):
        speak("没有消息")
        return
    total = len(data["messages"])
    read = sum(1 for m in data["messages"] if m.get("read") == 1)
    speak(f"共{total}条消息，已读{read}条，未读{total - read}条")


def _cancel_pending_delread() -> None:
    global PENDING_DEL_READ, DEL_READ_TIMER
    if PENDING_DEL_READ:
        PENDING_DEL_READ = False
        DEL_READ_TIMER = None
        log("delread auto-cancelled (timeout)")
        speak("删除操作已取消")


def action_delread(data: dict) -> None:
    global PENDING_DEL_READ, DEL_READ_TIMESTAMP, DEL_READ_TIMER
    PENDING_DEL_READ = True
    DEL_READ_TIMESTAMP = time.time()
    if DEL_READ_TIMER is not None:
        DEL_READ_TIMER.cancel()
    DEL_READ_TIMER = threading.Timer(DELREAD_TIMEOUT, _cancel_pending_delread)
    DEL_READ_TIMER.daemon = True
    DEL_READ_TIMER.start()
    speak(f"确认删除已读, 请在{DELREAD_TIMEOUT}秒内按确认")


def action_delread_confirm(data: dict) -> None:
    global PENDING_DEL_READ, DEL_READ_TIMER
    if DEL_READ_TIMER is not None:
        DEL_READ_TIMER.cancel()
        DEL_READ_TIMER = None
    PENDING_DEL_READ = False
    if time.time() - DEL_READ_TIMESTAMP > DELREAD_TIMEOUT:
        speak("已取消")
        return
    data["messages"] = [m for m in data["messages"] if m.get("read") != 1]
    data["current"] = data["messages"][0]["id"] if data["messages"] else 0
    save_messages(data)
    speak("已删除所有已读")


ACTIONS = {
    "enter":   action_enter,
    "pre":     action_pre,
    "next":    action_next,
    "all":     action_all,
    "delread": action_delread,
}

# ---------------- Command parser ----------------

def _strip_brackets(s: str) -> str:
    return s.replace("[", "").replace("]", "")


def check_patterns(data: dict) -> None:
    global BUFFER, LAST_ACTION_TIME, PENDING_DEL_READ

    now = int(time.monotonic() * 1000)
    if now - LAST_ACTION_TIME < DEBOUNCE_MS:
        BUFFER.clear()
        return

    raw = "".join(BUFFER)
    if "[" not in raw or "]" not in raw:
        return

    cmd = _strip_brackets(raw)
    matched = None
    for p in COMMAND_PATTERNS:
        if p in cmd:
            matched = p
            break

    if not matched:
        return

    LAST_ACTION_TIME = now
    BUFFER.clear()

    action_name = COMMAND_ALIASES[matched]
    action = ACTIONS.get(action_name)
    if not action:
        return

    if action_name == "enter" and PENDING_DEL_READ:
        action_delread_confirm(data)
        return

    if action_name != "delread":
        PENDING_DEL_READ = False

    action(data)

# ---------------- Device loop ----------------

def _find_keyboard() -> str | None:
    import subprocess
    for d in list_devices():
        try:
            p = subprocess.check_output(
                ["udevadm", "info", "--query=property", "--name=" + d]
            ).decode()
            if "ID_INPUT_KEYBOARD=1" in p and "ID_BUS=usb" in p:
                return d
        except Exception:
            continue
    return None


def device_loop() -> None:
    dev = None
    while True:
        try:
            if dev is None:
                path = _find_keyboard()
                if not path:
                    log("waiting keyboard...")
                    time.sleep(2)
                    continue
                dev = InputDevice(path)
                log(f"attached {path}")

            while select.select([dev.fd], [], [], 0)[0]:
                dev.read()

            for event in dev.read_loop():
                if event.type == ecodes.EV_KEY and event.value == 1:
                    key = ecodes.KEY.get(event.code)
                    if isinstance(key, list):
                        key = key[0]
                    ch = KEY_MAP.get(key, "")
                    if ch:
                        BUFFER.append(ch)
                        data = load_messages()
                        check_patterns(data)

        except Exception as e:
            log(f"loop error: {e}")
            dev = None
            time.sleep(2)

# ---------------- Main ----------------

def main() -> None:
    log("keyboard daemon started")
    resolve_adapter(None)  # warm up default adapter (starts worker thread)
    threading.Thread(target=watchdog_loop, daemon=True).start()
    device_loop()


if __name__ == "__main__":
    main()
