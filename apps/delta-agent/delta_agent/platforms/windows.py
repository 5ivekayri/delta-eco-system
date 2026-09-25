import os
from pathlib import Path
from .base import BasePlatformAdapter


class WindowsPlatformAdapter(BasePlatformAdapter):
    os_name = "windows"

    def open_path(self, path: str):
        os.startfile(path)

    def open_app(self, app_id: str):
        if app_id == "browser":
            self.open_url("https://example.com")
        elif app_id == "vscode":
            candidates = [Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Microsoft VS Code/Code.exe",
                          Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Microsoft VS Code/Code.exe"]
            executable = next((p for p in candidates if p.is_file()), None)
            if executable is None:
                raise RuntimeError("Visual Studio Code installation not found")
            os.startfile(str(executable))
        else:
            raise ValueError("Unsupported application")
