import pytest

from GramAddict.core import slack
from GramAddict.core.utils import is_newer_ig_version

TESTED = "300.0.0.29.110"


@pytest.mark.parametrize(
    "running, expected",
    [
        ("300.0.0.29.110", False),
        ("300.0.0.29.111", True),
        ("301.0.0.1.2", True),
        ("99.0.0.0.1", False),  # string compare said "9" > "3": newer
        ("1000.0.0.0.1", True),  # string compare said "1" < "3": older
        ("not found", False),
    ],
)
def test_is_newer_ig_version(running, expected):
    assert is_newer_ig_version(running, TESTED) is expected


def test_slack_notify_sends_to_account_webhook(monkeypatch):
    sent = []
    monkeypatch.setattr(slack, "load_slack_config", lambda u: {"slack-webhook-url": f"hook-{u}"})
    monkeypatch.setattr(slack, "slack_send_text", lambda url, text: sent.append((url, text)) or True)
    assert slack.slack_notify("me", "IG updated")
    assert sent == [("hook-me", "IG updated")]


def test_slack_notify_without_config_or_username(monkeypatch):
    monkeypatch.setattr(slack, "load_slack_config", lambda u: None)
    assert not slack.slack_notify("me", "x")
    assert not slack.slack_notify(None, "x")
