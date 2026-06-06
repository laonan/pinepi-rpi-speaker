#!/usr/bin/env python3
"""Scheduled voice reminder — designed for use with crontab.

Usage:
    python3 -m pinepi_speaker.remind "早安，今天是美好的一天"
    # or via the installed shell wrapper:
    pinepi-remind "早安，今天是美好的一天"

Crontab example (crontab -e):
    0 7 * * * /opt/pinepi-speaker/piper/say.sh "早安提醒"
    # or using this script for full TTS-adapter support:
    0 7 * * * python3 -m pinepi_speaker.remind "早安提醒"
"""

import os
import signal
import subprocess
import sys
import threading

from pinepi_speaker.tts.piper_adapter import _play_wav_blocking
from pinepi_speaker import config


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: pinepi-remind <text>", file=sys.stderr)
        sys.exit(1)

    text = " ".join(sys.argv[1:])
    done = threading.Event()

    def _run() -> None:
        try:
            _play_wav_blocking(config.BEEP_WAV)
            proc = subprocess.Popen(
                [config.PIPER_SAY_SH, text],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            try:
                proc.wait(timeout=120)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except Exception:
                    pass
                proc.wait()
            _play_wav_blocking(config.BEEP_DONE_WAV)
        except Exception as e:
            print(f"remind error: {e}", file=sys.stderr)
        finally:
            done.set()

    t = threading.Thread(target=_run, daemon=False)
    t.start()
    done.wait(timeout=130)


if __name__ == "__main__":
    main()
