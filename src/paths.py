# src/paths.py
import os
import sys


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def resource_path(name: str) -> str:
    """Path to a bundled asset in frozen builds, or /assets in dev."""
    if is_frozen():
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        for candidate in (
            os.path.join(base, name),
            os.path.join(base, "assets", name),
            os.path.join(os.path.dirname(sys.executable), "assets", name),
        ):
            if os.path.exists(candidate):
                return candidate
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