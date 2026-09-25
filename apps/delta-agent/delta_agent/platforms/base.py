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
                "architecture": platform.machine(), "username": getpass.getuser(), "agent_version": "0.1.0"}

    def open_url(self, url: str):
        if not webbrowser.open(url):
            raise RuntimeError("Browser could not be opened")

    def run(self, arguments: list[str]):
        subprocess.run(arguments, check=True, timeout=10, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False)

    @abstractmethod
    def open_path(self, path: str):
        pass

    @abstractmethod
    def open_app(self, app_id: str):
        pass
