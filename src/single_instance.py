# src/single_instance.py
import ctypes

ERROR_ALREADY_EXISTS = 183


class SingleInstance:
    def __init__(self, name="Local\\ChristmasOverlay_SingleInstance"):
        self.kernel32 = ctypes.windll.kernel32
        self.handle = self.kernel32.CreateMutexW(None, False, name)
        self.already_running = self.kernel32.GetLastError() == ERROR_ALREADY_EXISTS

    def release(self):
        if self.handle:
            self.kernel32.CloseHandle(self.handle)
            self.handle = None