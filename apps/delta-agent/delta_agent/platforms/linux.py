from .base import BasePlatformAdapter


class LinuxPlatformAdapter(BasePlatformAdapter):
    os_name = "linux"

    def open_path(self, path: str):
        self.run(["xdg-open", path])

    def open_app(self, app_id: str):
        if app_id == "browser":
            self.open_url("https://example.com")
        elif app_id == "vscode":
            self.run(["code", "--new-window"])
        else:
            raise ValueError("Unsupported application")
