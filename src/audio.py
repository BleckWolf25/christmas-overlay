# src/audio.py
import ctypes
from ctypes import wintypes
import io
import math
import os
import queue
import random
import struct
import tempfile
import threading
import wave
import winsound

from state import MUSIC_DIR

# Peaceful winter celesta / music-box notes (Hz): C5, D5, E5, G5, A5, C6
CHIME_NOTES = [523.25, 587.33, 659.25, 783.99, 880.00, 1046.50]
AUDIO_EXTENSIONS = (".mp3", ".wav", ".wma", ".m4a", ".flac", ".ogg")

_winmm = ctypes.windll.winmm
_winmm.mciSendStringW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.LPWSTR,
    wintypes.UINT,
    wintypes.HANDLE,
]
_winmm.mciSendStringW.restype = wintypes.DWORD


def _mci(cmd: str) -> tuple[int, str]:
    buf = ctypes.create_unicode_buffer(256)
    err = _winmm.mciSendStringW(cmd, buf, 256, None)
    return int(err), buf.value


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


def list_music_files() -> list[str]:
    """Finds audio files in the user's Windows Music folder (top-level and 1 level deep)."""
    if not os.path.isdir(MUSIC_DIR):
        return []
    found: list[str] = []
    try:
        for entry in os.scandir(MUSIC_DIR):
            if entry.name.startswith("."):
                continue
            if entry.is_file() and entry.name.lower().endswith(AUDIO_EXTENSIONS):
                found.append(entry.path)
            elif entry.is_dir():
                try:
                    for sub in os.scandir(entry.path):
                        if (
                            sub.is_file()
                            and not sub.name.startswith(".")
                            and sub.name.lower().endswith(AUDIO_EXTENSIONS)
                        ):
                            found.append(sub.path)
                except OSError:
                    continue
    except OSError:
        return []
    return sorted(found, key=lambda p: os.path.basename(p).lower())


class AudioManager:
    _ALIAS = "xmas_bgm"

    def __init__(self, initial_volume: int = 75, on_music_update=None):
        tmp = tempfile.gettempdir()
        pid = os.getpid()
        self.chime_path = os.path.join(tmp, f"xmas_chime_{pid}.wav")
        self.ambient_path = os.path.join(tmp, f"xmas_ambient_bell_{pid}.wav")
        self.ambient_chimes_on = False
        self.music_on = False
        self.is_playing = False
        self.is_paused = False
        self.volume = max(0, min(100, int(initial_volume)))
        self._on_music_update = on_music_update

        self._playlist: list[str] = []
        self._track_idx = 0
        self._opened_path: str | None = None

        self._ambient_stop = threading.Event()
        self._ambient_thread: threading.Thread | None = None

        self._cmd_q: queue.Queue[tuple[str, object]] = queue.Queue()
        self._worker_stop = threading.Event()
        self._music_thread = threading.Thread(
            target=self._music_worker, daemon=True
        )
        self._music_thread.start()

        try:
            with open(self.chime_path, "wb") as f:
                f.write(generate_bell_wav([659.25, 783.99, 1046.50], 0.11))
        except Exception:
            pass

    @property
    def current_track_name(self) -> str:
        if not self._playlist:
            files = list_music_files()
            if not files:
                return ""
            self._playlist = files
        idx = self._track_idx % len(self._playlist)
        return os.path.splitext(os.path.basename(self._playlist[idx]))[0]

    def _notify_music(self) -> None:
        if self._on_music_update:
            try:
                self._on_music_update()
            except Exception:
                pass

    def play_chime(self) -> None:
        """Plays UI feedback chime via WaveOut without disturbing MCI music playback."""
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
            try:
                winsound.PlaySound(None, 0)
            except Exception:
                pass

    def _ambient_loop(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set() and self.ambient_chimes_on:
            if self.is_playing:
                if stop_event.wait(4.0):
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
        """Enables or disables music playback. Resumes cleanly if paused."""
        if on:
            files = list_music_files()
            if not files:
                return False
            self._playlist = files
            self.music_on = True
            self._cmd_q.put(("play_or_resume", None))
        else:
            self.music_on = False
            self._cmd_q.put(("pause", None))
        return True

    def toggle_play_pause(self) -> bool:
        """Toggles between playing and paused without resetting or skipping tracks."""
        if self.is_playing:
            self.music_on = False
            self._cmd_q.put(("pause", None))
            return True
        return self.set_music_enabled(True)

    def next_track(self) -> bool:
        files = list_music_files()
        if not files:
            return False
        self._playlist = files
        self.music_on = True
        self._cmd_q.put(("next", None))
        return True

    def prev_track(self) -> bool:
        files = list_music_files()
        if not files:
            return False
        self._playlist = files
        self.music_on = True
        self._cmd_q.put(("prev", None))
        return True

    def set_volume(self, volume: int) -> None:
        self.volume = max(0, min(100, int(volume)))
        self._cmd_q.put(("volume", self.volume))

    def _mci_close(self) -> None:
        _mci(f"stop {self._ALIAS}")
        _mci(f"close {self._ALIAS}")
        self._opened_path = None

    def _mci_apply_volume(self) -> None:
        mci_vol = int(self.volume * 10)  # MCI volume range is 0..1000
        _mci(f"setaudio {self._ALIAS} volume to {mci_vol}")

    def _mci_open_and_play(self, idx: int) -> bool:
        if not self._playlist:
            self._playlist = list_music_files()
        if not self._playlist:
            self.music_on = False
            self.is_playing = False
            self.is_paused = False
            self._notify_music()
            return False

        self._track_idx = idx % len(self._playlist)
        path = self._playlist[self._track_idx]
        self._mci_close()

        safe_path = path.replace('"', '""')
        err, _ = _mci(f'open "{safe_path}" alias {self._ALIAS}')
        if err != 0:
            # Try skipping a corrupt/unsupported file once
            if len(self._playlist) > 1:
                self._track_idx = (self._track_idx + 1) % len(self._playlist)
                safe_path = self._playlist[self._track_idx].replace('"', '""')
                err, _ = _mci(f'open "{safe_path}" alias {self._ALIAS}')
            if err != 0:
                self.music_on = False
                self.is_playing = False
                self.is_paused = False
                self._notify_music()
                return False

        self._opened_path = self._playlist[self._track_idx]
        _mci(f"set {self._ALIAS} time format milliseconds")
        self._mci_apply_volume()
        _mci(f"play {self._ALIAS}")
        self.is_playing = True
        self.is_paused = False
        self._notify_music()
        return True

    def _music_worker(self) -> None:
        while not self._worker_stop.is_set():
            try:
                cmd, arg = self._cmd_q.get(timeout=0.45)
            except queue.Empty:
                # Poll end-of-track when playing
                if self.music_on and self.is_playing and self._opened_path:
                    err, mode = _mci(f"status {self._ALIAS} mode")
                    if err == 0 and mode.strip().lower() == "stopped":
                        self._mci_open_and_play(self._track_idx + 1)
                continue

            if cmd == "quit":
                self._mci_close()
                break
            elif cmd == "play_or_resume":
                if self.is_paused and self._opened_path and os.path.exists(self._opened_path):
                    err, _ = _mci(f"resume {self._ALIAS}")
                    if err != 0:
                        _mci(f"play {self._ALIAS}")
                    self._mci_apply_volume()
                    self.is_playing = True
                    self.is_paused = False
                    self._notify_music()
                elif not self.is_playing:
                    self._mci_open_and_play(self._track_idx)
            elif cmd == "pause":
                if self.is_playing and self._opened_path:
                    _mci(f"pause {self._ALIAS}")
                    self.is_playing = False
                    self.is_paused = True
                    self._notify_music()
            elif cmd == "next":
                self._mci_open_and_play(self._track_idx + 1)
            elif cmd == "prev":
                # Restart current track if more than 3 seconds in; otherwise go previous
                go_prev = True
                if self._opened_path:
                    err, pos_str = _mci(f"status {self._ALIAS} position")
                    if err == 0 and pos_str.strip().isdigit() and int(pos_str.strip()) > 3000:
                        go_prev = False
                target = (self._track_idx - 1) if go_prev else self._track_idx
                self._mci_open_and_play(target)
            elif cmd == "volume":
                if self._opened_path:
                    self._mci_apply_volume()
                self._notify_music()

    def cleanup(self) -> None:
        self.ambient_chimes_on = False
        self.music_on = False
        self.is_playing = False
        self.is_paused = False
        self._ambient_stop.set()
        self._worker_stop.set()
        self._cmd_q.put(("quit", None))
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