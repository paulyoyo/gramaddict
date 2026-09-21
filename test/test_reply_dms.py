"""Focused checks for the two-step DM auto-reply feature.

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


def test_enqueue_get_remove_and_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        s = _new_storage(tmp)
        assert s.get_pending_replies() == []

        s.enqueue_pending_reply("alice")
        s.enqueue_pending_reply("alice")  # idempotent
        s.enqueue_pending_reply("bob")
        names = [e["username"] for e in s.get_pending_replies()]
        assert names == ["alice", "bob"], names

        # Persisted to disk and reloaded on a fresh Storage
        s2 = _new_storage(tmp)
        assert [e["username"] for e in s2.get_pending_replies()] == ["alice", "bob"]

        s2.remove_pending_reply("alice")
        assert [e["username"] for e in s2.get_pending_replies()] == ["bob"]
        s2.remove_pending_reply("nobody")  # no-op, must not raise
        assert [e["username"] for e in s2.get_pending_replies()] == ["bob"]


def test_add_interacted_user_enqueues_only_on_pm():
    with tempfile.TemporaryDirectory() as tmp:
        s = _new_storage(tmp)
        s.add_interacted_user("noreply", session_id="s1", liked=1)  # pm_sent defaults False
        assert s.get_pending_replies() == []
        s.add_interacted_user("pmd", session_id="s1", pm_sent=True)
        assert [e["username"] for e in s.get_pending_replies()] == ["pmd"]


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


def test_deepseek_sentinel_passthrough(monkeypatch=None):
    class FakeResp:
        def __init__(self, content):
            self._content = content

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": self._content}}]}

    cfg = {"deepseek-api-key": "sk-test"}

    # Sentinel is returned verbatim so the caller can branch to manual handoff.
    deepseek_mod.requests.post = lambda *a, **k: FakeResp(deepseek_mod.NO_REPLY)
    assert deepseek_mod.generate_reply(cfg, "hola") == deepseek_mod.NO_REPLY

    # Normal reply passes through (trimmed).
    deepseek_mod.requests.post = lambda *a, **k: FakeResp("  hey there  ")
    assert deepseek_mod.generate_reply(cfg, "hola") == "hey there"

    # Network/parse error -> None (treated as needs-manual by caller).
    def boom(*a, **k):
        raise RuntimeError("network down")

    deepseek_mod.requests.post = boom
    assert deepseek_mod.generate_reply(cfg, "hola") is None

    # Missing api key -> None, no call made.
    assert deepseek_mod.generate_reply({}, "hola") is None


if __name__ == "__main__":
    test_enqueue_get_remove_and_idempotent()
    test_add_interacted_user_enqueues_only_on_pm()
    test_min_hours_filter()
    test_deepseek_sentinel_passthrough()
    print("all reply-dms checks passed")
