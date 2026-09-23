import subprocess
from types import SimpleNamespace

import pytest

from GramAddict.core import adb as adb_mod
from GramAddict.core.adb import AdbError, adb, device_quote


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake_run(cmd, **kwargs):
        seen.append((cmd, kwargs))
        return SimpleNamespace(returncode=seen_rc[0], stdout="", stderr="boom")

    seen_rc = [0]
    monkeypatch.setattr(adb_mod.subprocess, "run", fake_run)
    return seen, seen_rc


def test_builds_arg_list_without_host_shell(calls):
    seen, _ = calls
    adb("emulator-5554", "shell", "input", "keyevent", 66)
    cmd, kwargs = seen[0]
    assert cmd == ["adb", "-s", "emulator-5554", "shell", "input", "keyevent", "66"]
    assert "shell" not in kwargs


def test_no_device_id_omits_serial(calls):
    seen, _ = calls
    adb(None, "devices")
    assert seen[0][0] == ["adb", "devices"]


def test_check_error_hides_arguments(calls):
    _, rc = calls
    rc[0] = 1
    with pytest.raises(AdbError) as exc:
        adb(None, "shell", "input", "text", device_quote("s3cr3t;pw"), check=True)
    assert "s3cr3t" not in str(exc.value)


def test_device_quote_keeps_url_query_intact():
    url = "https://www.instagram.com/p/abc/?igsh=x&utm_source=y"
    assert device_quote(url) == f"'{url}'"
    assert device_quote("pa$$ word") == "'pa$$ word'"


def test_real_subprocess_receives_list(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured.update(cmd=cmd, **kwargs)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(adb_mod.subprocess, "run", fake_run)
    adb("dev", "shell", "am", "start", "-d", device_quote("a&b"))
    assert isinstance(captured["cmd"], list)
    assert captured["cmd"][-1] == "'a&b'"
