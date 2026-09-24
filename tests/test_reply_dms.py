"""Focused checks for the DJ two-step DM flow: the pending-reply queue in
Storage and the DeepSeek classifier (the real modules, not copies)."""
from datetime import datetime, timedelta

import pytest

from GramAddict.core import deepseek as deepseek_mod
from GramAddict.core import storage as storage_mod
from GramAddict.plugins.action_reply_dms import ActionReplyDMs


@pytest.fixture
def new_storage(tmp_path, monkeypatch):
    """Storage("tester") with its account files in a temp dir."""
    monkeypatch.setattr(storage_mod, "ACCOUNTS", str(tmp_path))
    return lambda: storage_mod.Storage("tester")


def _hours_ago(hours):
    return (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S.%f")


def test_queue_enqueue_update_remove(new_storage):
    s = new_storage()
    assert s.get_pending_replies() == []

    s.enqueue_pending_reply("alice", stage="greeted", first_name="Alice", source="@club")
    s.enqueue_pending_reply("alice", stage="greeted")  # idempotent
    s.enqueue_pending_reply("bob", stage="greeted", first_name="Bob", source=None)
    q = s.get_pending_replies()
    assert [e["username"] for e in q] == ["alice", "bob"]
    assert q[0]["stage"] == "greeted"
    assert q[0]["first_name"] == "Alice"
    assert q[0]["source"] == "@club"

    # Advance a stage (and refresh sent_at)
    s.update_pending_reply("alice", stage="sent_youtube", sent_at="2020-01-01 00:00:00.000000")
    s2 = new_storage()  # reload from disk
    alice = next(e for e in s2.get_pending_replies() if e["username"] == "alice")
    assert alice["stage"] == "sent_youtube"
    assert alice["sent_at"] == "2020-01-01 00:00:00.000000"

    s2.remove_pending_reply("alice")
    assert [e["username"] for e in s2.get_pending_replies()] == ["bob"]
    s2.remove_pending_reply("nobody")  # no-op, must not raise
    assert [e["username"] for e in s2.get_pending_replies()] == ["bob"]


def test_add_interacted_user_does_not_touch_queue(new_storage):
    # pm_list sending is kept separate from the DJ conversation queue.
    s = new_storage()
    s.add_interacted_user("pmd", session_id="s1", pm_sent=True)
    assert s.get_pending_replies() == []


def test_hours_since_used_for_min_hours():
    hours_since = ActionReplyDMs._hours_since
    assert 3.9 < hours_since(_hours_ago(4)) < 4.1
    assert hours_since(_hours_ago(1)) < 3
    # missing or unreadable timestamps count as "long ago", so they get checked
    assert hours_since(None) == float("inf")
    assert hours_since("not a date") == float("inf")


def test_classify_intent(monkeypatch):
    class FakeResp:
        status_code = 200

        def __init__(self, content):
            self._content = content

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": self._content}}]}

    cfg = {"deepseek-api-key": "sk-test"}

    for content, expected in [
        ("YES", deepseek_mod.YES),
        ("yes, definitely", deepseek_mod.YES),
        ("**YES**", deepseek_mod.YES),
        ("NO", deepseek_mod.NO),
        ("no thanks", deepseek_mod.NO),
        ("NOT SURE", deepseek_mod.UNSURE),
        ("maybe later", deepseek_mod.UNSURE),
        ("¿quién eres?", deepseek_mod.UNSURE),
    ]:
        monkeypatch.setattr(deepseek_mod.requests, "post", lambda *a, _c=content, **k: FakeResp(_c))
        assert deepseek_mod.classify_intent(cfg, "Interested?", "x") == expected, content

    # Unexpected error -> ERROR (the caller keeps the user queued, no handoff)
    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(deepseek_mod.requests, "post", boom)
    assert deepseek_mod.classify_intent(cfg, "Interested?", "x") == deepseek_mod.ERROR

    # Missing api key -> ERROR, no call
    assert deepseek_mod.classify_intent({}, "Interested?", "x") == deepseek_mod.ERROR
