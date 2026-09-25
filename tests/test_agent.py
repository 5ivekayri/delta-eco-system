from unittest.mock import Mock
import pytest
from delta_agent.commands import CommandExecutor
from delta_agent.main import persistent_uid
from delta_agent.platforms import get_platform


@pytest.mark.parametrize('name,expected', [('darwin','macos'),('win32','windows'),('linux','linux')])
def test_platform_detection(name, expected):
    adapter = get_platform(name)
    assert adapter.os_name == expected
    assert set(adapter.capabilities) == {'system_info','open_url','open_path','open_app'}


def test_allowlist_urls_and_paths(tmp_path):
    adapter = Mock()
    executor = CommandExecutor(adapter, [str(tmp_path)])
    def execute(action, payload):
        return executor.execute({'type':'command','command_id':'test','action':action,'payload':payload})
    assert execute('open_url', {'url':'https://example.com'})['success']
    adapter.open_url.assert_called_once_with('https://example.com')
    assert not execute('execute_shell', {'command':'echo unsafe'})['success']
    assert not execute('open_url', {'url':'javascript:alert(1)'})['success']
    assert not execute('open_app', {'app_id':'/bin/sh'})['success']
    assert not execute('open_path', {'path':str(tmp_path.parent)})['success']
    file = tmp_path/'executable.sh'
    file.write_text('echo unsafe')
    assert not execute('open_path', {'path':str(file)})['success']
    assert execute('open_path', {'path':str(tmp_path)})['success']


def test_uid_persists(tmp_path):
    assert persistent_uid(tmp_path) == persistent_uid(tmp_path)
