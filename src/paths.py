# src/paths.py
import os
import sys

def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def resource_path(name: str) -> str:
    """Path to a file bundled with --add-data. In dev = look in /assets."""
    if is_frozen():
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        return os.path.join(base, name)

    dev_assets = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets"
    )
    if os.path.exists(os.path.join(dev_assets, name)):
        return os.path.join(dev_assets, name)

    return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)


def exe_path() -> str:
    """Full path of the running executable."""
    return sys.executable