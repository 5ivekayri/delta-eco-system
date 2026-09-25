import sys
from .base import BasePlatformAdapter
from .linux import LinuxPlatformAdapter
from .macos import MacOSPlatformAdapter
from .windows import WindowsPlatformAdapter


def get_platform(platform: str | None = None) -> BasePlatformAdapter:
    name = platform or sys.platform
    if name == "darwin":
        return MacOSPlatformAdapter()
    if name == "win32":
        return WindowsPlatformAdapter()
    if name.startswith("linux"):
        return LinuxPlatformAdapter()
    raise ValueError(f"Unsupported platform: {name}")
