"""Batch 11: secrets stay out of logs, external calls can't hang forever."""
import logging
import subprocess

import pytest
import requests

from GramAddict.core import adb as adb_mod
from GramAddict.core import slack, utils
from GramAddict.core.adb import AdbError, adb
from GramAddict.core.log import redact
from GramAddict.plugins import telegram

TOKEN = "123456:ABC-secret-token"
WEBHOOK = "https://hooks.slack.com/services/T000/B000/SECRETSECRET"


def test_redact_blanks_the_value_and_its_url_path():
    msg = (
        "HTTPSConnectionPool(host='hooks.slack.com'): Max retries exceeded with url: "
        "/services/T000/B000/SECRETSECRET (Caused by timeout)"
    )
    assert "SECRET" not in redact(msg, WEBHOOK)
    assert redact(f"url: /bot{TOKEN}/sendMessage", TOKEN) == "url: /bot***/sendMessage"
    assert redact("nothing to hide", None, "") == "nothing to hide"


def _raise(exc):
    def fake(*a, **k):
        raise exc

    return fake


def test_slack_error_log_has_no_webhook(monkeypatch, caplog):
    err = requests.ConnectionError(
        "Max retries exceeded with url: /services/T000/B000/SECRETSECRET"
    )
    monkeypatch.setattr(slack.requests, "post", _raise(err))
    with caplog.at_level(logging.ERROR):
        assert slack.slack_send_text(WEBHOOK, "hi") is False
    assert "SECRETSECRET" not in caplog.text and "Error sending Slack message" in caplog.text


def test_telegram_has_timeout_and_no_token_in_log(monkeypatch, caplog):
    seen = {}

    def get(url, params=None, timeout=None):
        seen["timeout"] = timeout
        raise requests.ConnectionError(f"Max retries exceeded with url: /bot{TOKEN}/sendMessage")

    monkeypatch.setattr(telegram.requests, "get", get)
    with caplog.at_level(logging.ERROR):
        assert telegram.telegram_bot_send_text(TOKEN, "chat", "hi") is None
    assert seen["timeout"] == 15
    assert TOKEN not in caplog.text and "ABC-secret" not in caplog.text


def test_update_check_offline_does_not_crash(monkeypatch):
    monkeypatch.setattr(utils.requests, "get", _raise(requests.ConnectionError("offline")))
    assert utils.update_available() == (False, None)


def _hung(*a, **k):
    raise subprocess.TimeoutExpired(a[0], k.get("timeout"))


def test_adb_timeout_returns_an_empty_result(monkeypatch, caplog):
    monkeypatch.setattr(adb_mod.subprocess, "run", _hung)
    with caplog.at_level(logging.WARNING):
        result = adb("dev", "shell", "input", "text", "s3cret")
    assert result.returncode == -1 and result.stdout == ""
    assert "timed out" in caplog.text and "s3cret" not in caplog.text


def test_adb_timeout_with_check_raises(monkeypatch):
    monkeypatch.setattr(adb_mod.subprocess, "run", _hung)
    with pytest.raises(AdbError) as exc:
        adb("dev", "shell", "input", "text", "s3cret", check=True)
    assert "s3cret" not in str(exc.value)


def test_adb_passes_a_timeout(monkeypatch):
    seen = {}

    def run(cmd, **kw):
        seen.update(kw)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(adb_mod.subprocess, "run", run)
    adb(None, "devices")
    assert seen["timeout"] == 60
