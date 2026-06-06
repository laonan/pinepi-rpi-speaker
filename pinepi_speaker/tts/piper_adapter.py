"""Piper TTS adapter (local, privacy-preserving).

Audio pipeline:
  beep → piper binary via say.sh → aplay → beep_done

All audio is serialised through a single worker thread so nothing overlaps.
Each TTS subprocess runs in its own session (setsid) so the whole process
tree can be killed cleanly on timeout.
"""

import math
import os
import signal
import struct
import subprocess
import threading
import time
from queue import Queue

from pinepi_speaker import config
from pinepi_speaker.tts.base import TTSAdapter


def _generate_beep_wav(path: str, freq: int = 1000, duration_ms: int = 80,
                       volume: float = 0.5, sample_rate: int = 16000) -> None:
    n_samples = int(sample_rate * duration_ms / 1000)
    samples = b""
    for i in range(n_samples):
        val = int(volume * 32767 * math.sin(2 * math.pi * freq * i / sample_rate))
        samples += struct.pack("<h", val)
    data_size = len(samples)
    header = struct.pack("<4sI4s", b"RIFF", 36 + data_size, b"WAVE")
    header += struct.pack("<4sIHHIIHH", b"fmt ", 16, 1, 1,
                         sample_rate, sample_rate * 2, 2, 16)
    header += struct.pack("<4sI", b"data", data_size)
    with open(path, "wb") as f:
        f.write(header + samples)


def _play_wav_blocking(path: str) -> None:
    try:
        output = config.audio_output()
        if output == "pulse":
            cmd = ["paplay", "--device", config.pulse_sink(), path]
        else:
            cmd = ["aplay", "-q", "-D", config.alsa_device(), path]
        subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except Exception:
        pass


class PiperAdapter(TTSAdapter):
    """Wraps the local Piper binary via ``say.sh``.

    A background worker thread serialises all audio so beep/TTS/beep-done
    never overlap. Call :meth:`start` once after construction (or use the
    module-level singleton :data:`piper`).
    """

    def __init__(self) -> None:
        self._queue: Queue = Queue()
        self._worker_thread: threading.Thread | None = None
        self._log = self._default_log

    def _default_log(self, msg: str) -> None:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"{ts} [piper] {msg}"
        try:
            with open(config.LOG_FILE, "a") as f:
                f.write(line + "\n")
        except Exception:
            pass
        print(line, flush=True)

    def set_logger(self, log_fn) -> None:
        self._log = log_fn

    def start(self) -> None:
        """Generate beep WAVs and start the worker thread."""
        _generate_beep_wav(config.BEEP_WAV, freq=1000, duration_ms=80)
        _generate_beep_wav(config.BEEP_DONE_WAV, freq=600, duration_ms=120)
        self._worker_thread = threading.Thread(
            target=self._worker, daemon=True, name="piper-tts-worker"
        )
        self._worker_thread.start()

    def speak(self, text: str) -> None:
        self._queue.put(text)

    def _worker(self) -> None:
        while True:
            text = self._queue.get()
            if text is None:
                continue
            try:
                self._log(f"TTS PLAY: {text}")
                _play_wav_blocking(config.BEEP_WAV)

                proc = subprocess.Popen(
                    [config.PIPER_SAY_SH, text,
                     config.piper_model(),
                     config.audio_output(),
                     config.alsa_device() if config.audio_output() != "pulse" else config.pulse_sink()],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                try:
                    rc = proc.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    self._log("TTS timeout, killing process group")
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except Exception:
                        pass
                    proc.wait()
                    rc = -9

                self._log(f"TTS exit {rc}")
                _play_wav_blocking(config.BEEP_DONE_WAV)

            except Exception as e:
                self._log(f"TTS ERROR: {e}")

    def shutdown(self) -> None:
        self._queue.put(None)
