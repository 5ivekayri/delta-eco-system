from abc import ABC, abstractmethod
import getpass
import platform
import socket
import subprocess
import webbrowser


class BasePlatformAdapter(ABC):
    os_name = "unknown"
    capabilities = ["system_info", "open_url", "open_path", "open_app"]

    def get_system_info(self) -> dict:
        return {"hostname": socket.gethostname(), "os": self.os_name,
                "architecture": platform.machine(), "username": getpass.getuser(), "agent_version": "0.2.0"}

    def open_url(self, url: str):
        if not webbrowser.open(url):
            raise RuntimeError("Browser could not be opened")

    def installed_applications(self):
        from delta_agent.applications import discover
        return discover(self.os_name)

    def open_installed_app(self, app_id: str):
        # Resolve again locally at execution time. Never accept a caller's path.
        app = self.installed_applications().get(app_id)
        if app is None:
            raise ValueError('Application is no longer installed')
        if self.os_name == 'macos':
            self.run(['/usr/bin/open', '-a', str(app.path)])
        elif self.os_name == 'linux':
            self.run(['gio', 'launch', str(app.path)])
        elif self.os_name == 'windows':
            import os
            os.startfile(str(app.path))
        else:
            raise ValueError('Unsupported platform')

    def run(self, arguments: list[str]):
        subprocess.run(arguments, check=True, timeout=10, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False)

    @abstractmethod
    def open_path(self, path: str):
        pass

    @abstractmethod
    def open_app(self, app_id: str):
        pass
