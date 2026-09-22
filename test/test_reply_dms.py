"""Focused checks for the DJ two-step DM flow.

Modules are loaded standalone (by file path) so these run without the heavy
uiautomator2/colorama device stack — only atomicwrites/requests are needed.
Run: python -m pytest test/test_reply_dms.py  (or just execute the file).
"""
import importlib.util
import os
import tempfile
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, relpath))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


storage_mod = _load("gramaddict_storage", "GramAddict/core/storage.py")
deepseek_mod = _load("gramaddict_deepseek", "GramAddict/core/deepseek.py")


def _new_storage(tmp):
    storage_mod.ACCOUNTS = tmp  # redirect account files into the temp dir
    return storage_mod.Storage("tester")


def _hours_ago(hours):
    return (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S.%f")


def test_queue_enqueue_update_remove():
    with tempfile.TemporaryDirectory() as tmp:
        s = _new_storage(tmp)
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
        s2 = _new_storage(tmp)  # reload from disk
        alice = next(e for e in s2.get_pending_replies() if e["username"] == "alice")
        assert alice["stage"] == "sent_youtube"
        assert alice["sent_at"] == "2020-01-01 00:00:00.000000"

        s2.remove_pending_reply("alice")
        assert [e["username"] for e in s2.get_pending_replies()] == ["bob"]
        s2.remove_pending_reply("nobody")  # no-op, must not raise
        assert [e["username"] for e in s2.get_pending_replies()] == ["bob"]


def test_add_interacted_user_does_not_touch_queue():
    # pm_list sending is kept separate from the DJ conversation queue.
    with tempfile.TemporaryDirectory() as tmp:
        s = _new_storage(tmp)
        s.add_interacted_user("pmd", session_id="s1", pm_sent=True)
        assert s.get_pending_replies() == []


def test_min_hours_filter():
    # Mirrors the plugin's filter: keep entries whose sent_at is >= min_hours old.
    with tempfile.TemporaryDirectory() as tmp:
        s = _new_storage(tmp)
        s.pending_replies = [
            {"username": "old", "sent_at": _hours_ago(4)},
            {"username": "fresh", "sent_at": _hours_ago(1)},
        ]
        min_hours = 3

        def hours_since(ts):
            return (datetime.now() - datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f")).total_seconds() / 3600

        due = [e["username"] for e in s.get_pending_replies() if hours_since(e["sent_at"]) >= min_hours]
        assert due == ["old"], due


def test_classify_intent():
    class FakeResp:
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
        ("NO", deepseek_mod.NO),
        ("no thanks", deepseek_mod.NO),
        ("maybe later", deepseek_mod.UNSURE),
        ("¿quién eres?", deepseek_mod.UNSURE),
    ]:
        deepseek_mod.requests.post = lambda *a, **k: FakeResp(content)
        assert deepseek_mod.classify_intent(cfg, "Interested?", "x") == expected, content

    # Network error -> UNSURE (falls back to human)
    def boom(*a, **k):
        raise RuntimeError("network down")

    deepseek_mod.requests.post = boom
    assert deepseek_mod.classify_intent(cfg, "Interested?", "x") == deepseek_mod.UNSURE

    # Missing api key -> UNSURE, no call
    assert deepseek_mod.classify_intent({}, "Interested?", "x") == deepseek_mod.UNSURE


if __name__ == "__main__":
    test_queue_enqueue_update_remove()
    test_add_interacted_user_does_not_touch_queue()
    test_min_hours_filter()
    test_classify_intent()
    print("all DJ DM-flow checks passed")
