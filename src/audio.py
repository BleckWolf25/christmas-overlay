# src/audio.py
import glob
import io
import math
import os
import random
import struct
import tempfile
import threading
import wave
import winsound

from state import MUSIC_DIR

# Peaceful winter celesta / music-box notes (Hz): C5, D5, E5, G5, A5, C6
CHIME_NOTES = [523.25, 587.33, 659.25, 783.99, 880.00, 1046.50]

def generate_bell_wav(freqs: list[float], note_spacing: float = 0.14) -> bytes:
    sr = 44100
    duration = note_spacing * len(freqs) + 0.9
    total_samples = int(sr * duration)
    buf = [0.0] * total_samples

    for idx, freq in enumerate(freqs):
        start = int(idx * note_spacing * sr)
        for i in range(start, total_samples):
            t = (i - start) / sr
            env = math.exp(-t * 5.5) * min(1.0, t * 120.0)
            sample = (
                1800.0 * env * math.sin(2.0 * math.pi * freq * t)
                + 600.0 * math.exp(-t * 9.0) * math.sin(2.0 * math.pi * (freq * 2.0) * t)
            )
            buf[i] += sample

    f = io.BytesIO()
    with wave.open(f, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = b"".join(
            struct.pack("<h", max(-32768, min(32767, int(v)))) for v in buf
        )
        w.writeframes(frames)
    f.seek(0)
    return f.read()

def _wav_duration(path: str) -> float:
    try:
        with wave.open(path, "r") as w:
            rate = w.getframerate() or 44100
            return max(0.5, w.getnframes() / rate)
    except Exception:
        return 3.0

def _list_music_files() -> list[str]:
    if not os.path.isdir(MUSIC_DIR):
        return []
    return sorted(glob.glob(os.path.join(MUSIC_DIR, "*.wav")))

class AudioManager:
    def __init__(self):
        tmp = tempfile.gettempdir()
        pid = os.getpid()
        self.chime_path = os.path.join(tmp, f"xmas_chime_{pid}.wav")
        self.ambient_path = os.path.join(tmp, f"xmas_ambient_bell_{pid}.wav")
        self.ambient_chimes_on = False
        self.music_on = False

        self._ambient_stop = threading.Event()
        self._music_stop = threading.Event()
        self._ambient_thread: threading.Thread | None = None
        self._music_thread: threading.Thread | None = None

        try:
            with open(self.chime_path, "wb") as f:
                f.write(generate_bell_wav([659.25, 783.99, 1046.50], 0.11))
        except Exception:
            pass

    def play_chime(self) -> None:
        try:
            winsound.PlaySound(
                self.chime_path,
                winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
            )
        except Exception:
            pass

    def set_ambient_chimes(self, on: bool) -> None:
        if on == self.ambient_chimes_on and (
            not on or (self._ambient_thread and self._ambient_thread.is_alive())
        ):
            return

        self.ambient_chimes_on = on
        if on:
            self._ambient_stop.set()
            if self._ambient_thread and self._ambient_thread.is_alive():
                self._ambient_thread.join(timeout=0.5)
            stop_ev = threading.Event()
            self._ambient_stop = stop_ev
            self._ambient_thread = threading.Thread(
                target=self._ambient_loop, args=(stop_ev,), daemon=True
            )
            self._ambient_thread.start()
        else:
            self._ambient_stop.set()
            if not self.music_on:
                try:
                    winsound.PlaySound(None, 0)
                except Exception:
                    pass

    def _ambient_loop(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set() and self.ambient_chimes_on:
            if self.music_on:
                if stop_event.wait(5.0):
                    break
                continue
            phrase = random.sample(CHIME_NOTES, 3)
            try:
                with open(self.ambient_path, "wb") as f:
                    f.write(generate_bell_wav(phrase, 0.22))
                winsound.PlaySound(
                    self.ambient_path,
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
                )
            except Exception:
                pass

            wait_s = random.uniform(25.0, 40.0)
            if stop_event.wait(wait_s):
                break

    def set_music_enabled(self, on: bool) -> bool:
        """Returns False if turning on but no .wav files are present."""
        if on and not _list_music_files():
            return False

        if on == self.music_on and (
            not on or (self._music_thread and self._music_thread.is_alive())
        ):
            return True

        self.music_on = on
        if on:
            self._music_stop.set()
            if self._music_thread and self._music_thread.is_alive():
                self._music_thread.join(timeout=0.5)
            stop_ev = threading.Event()
            self._music_stop = stop_ev
            self._music_thread = threading.Thread(
                target=self._music_loop, args=(stop_ev,), daemon=True
            )
            self._music_thread.start()
        else:
            self._music_stop.set()
            if not self.ambient_chimes_on:
                try:
                    winsound.PlaySound(None, 0)
                except Exception:
                    pass
        return True

    def _music_loop(self, stop_event: threading.Event) -> None:
        files = _list_music_files()
        if not files:
            return
        idx = 0
        while not stop_event.is_set() and self.music_on:
            if self.ambient_chimes_on:
                if stop_event.wait(5.0):
                    break
                continue
            path = files[idx % len(files)]
            idx += 1
            try:
                dur = _wav_duration(path)
                winsound.PlaySound(
                    path,
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
                )
            except Exception:
                dur = 3.0
            # short gap between tracks
            if stop_event.wait(dur + 1.5):
                break

    def cleanup(self) -> None:
        self.ambient_chimes_on = False
        self.music_on = False
        self._ambient_stop.set()
        self._music_stop.set()
        try:
            winsound.PlaySound(None, 0)
        except Exception:
            pass
        for path in (self.chime_path, self.ambient_path):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass