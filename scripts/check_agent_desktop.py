"""Headless Qt smoke checks; run with the standalone Agent build environment."""
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from concurrent.futures import Future
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT/'apps/delta-agent'), str(ROOT/'shared/contracts')]
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication, QDialog, QPushButton
from delta_agent.desktop import AgentWindow, DesktopOpener


def main():
    app = QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        window = AgentWindow(Path(directory))
        window.show()
        app.processEvents()
        assert window.connect_button.isEnabled()
        assert not window.disconnect_button.isEnabled()
        assert not window.urls.isChecked()
        assert window.username.isVisible() and window.password.isVisible()
        assert not window.server.isVisible() and not window.roots.isVisible()
        assert not window.log.isVisible() and not window.devices.isVisible()
        window.open_settings()
        app.processEvents()
        assert window.access_mode.isVisible() and window.roots.isVisible()
        assert not window.server.isVisible()
        window.settings_tabs.setCurrentIndex(1)
        app.processEvents()
        assert window.server.isVisible()
        assert not window.log.isVisible()
        window.settings_dialog.hide()
        window.pages.setCurrentIndex(1)
        app.processEvents()
        assert window.chat.isVisible() and not window.password.isVisible()
        window.chat.setPlainText('private conversation')
        window.reset_dashboard()
        assert window.chat.toPlainText() == '' and window.pages.currentIndex() == 0
        window.grab().save(str(ROOT/'.runtime/desktop-login-clean.png'))
        window.tray.hide()
        window.hide()
        opener = DesktopOpener()
        for accepted in [True, False]:
            results = []
            def action():
                try:
                    opener.open_path(directory)
                    results.append('ok')
                except RuntimeError:
                    results.append('rejected')
            with patch('delta_agent.desktop.QDesktopServices.openUrl', return_value=accepted) as native:
                thread = threading.Thread(target=action)
                thread.start()
                deadline = time.monotonic() + 5
                while thread.is_alive() and time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(.01)
                thread.join(timeout=1)
                assert not thread.is_alive()
                assert results == (['ok'] if accepted else ['rejected'])
                native.assert_called_once()
        future = Future()
        future.cancel()
        with patch('delta_agent.desktop.QDesktopServices.openUrl') as native:
            opener.open_native((QUrl.fromLocalFile(directory), future))
            native.assert_not_called()
        # Real Qt approval buttons: allow, deny, closing, expiry and disconnect.
        for decision in ['allow', 'deny', 'close', 'expire', 'disconnect']:
            results = []
            cancelled = threading.Event()
            expires = time.time() + (1.2 if decision == 'expire' else 5)
            thread = threading.Thread(target=lambda: results.append(window.approvals.confirm(
                'open_url', {'url':'https://example.com'}, expires, cancelled)))
            thread.start()
            deadline = time.monotonic()+6
            acted = False
            while thread.is_alive() and time.monotonic()<deadline:
                app.processEvents()
                dialogs = [d for d in window.findChildren(QDialog) if d.isVisible() and d.windowTitle().startswith('Delta —')]
                if dialogs and not acted:
                    dialog = dialogs[0]
                    if decision in ['allow','deny']:
                        label = 'Разрешить один раз' if decision == 'allow' else 'Отклонить'
                        next(b for b in dialog.findChildren(QPushButton) if b.text()==label).click()
                    elif decision == 'close':
                        dialog.reject()
                    elif decision == 'disconnect':
                        cancelled.set()
                    acted = True
                time.sleep(.01)
            thread.join(timeout=1)
            assert not thread.is_alive()
            assert results == [decision == 'allow']
            for _ in range(15):
                app.processEvents(); time.sleep(.01)
            assert not [d for d in window.findChildren(QDialog) if d.isVisible() and d.windowTitle().startswith('Delta —')]
        window.hide()
        window.deleteLater()
        app.processEvents()
    print('Qt onboarding and native-opener dispatch checks passed')


if __name__ == '__main__':
    main()
