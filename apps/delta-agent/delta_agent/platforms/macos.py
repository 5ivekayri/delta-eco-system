from .base import BasePlatformAdapter


class MacOSPlatformAdapter(BasePlatformAdapter):
    os_name = "macos"

    def open_path(self, path: str):
        self.run(["/usr/bin/open", path])

    def open_app(self, app_id: str):
        if app_id == "browser":
            self.open_url("https://example.com")
        elif app_id == "vscode":
            self.run(["/usr/bin/open", "-a", "Visual Studio Code"])
        else:
            raise ValueError("Unsupported application")
