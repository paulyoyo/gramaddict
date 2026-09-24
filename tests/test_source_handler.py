from datetime import datetime
from types import SimpleNamespace

import pytest

from GramAddict.core import utils
from GramAddict.core.source_context import Percentages, SourceContext
from GramAddict.core.sources.base import SourceHandler
from GramAddict.core.storage import FollowingStatus


class FakeStore:
    def __init__(self, blacklist=(), interacted=None, reinteract=False):
        self.blacklist = set(blacklist)
        self.interacted = interacted or {}
        self.reinteract = reinteract
        self.added, self.queued, self.reinteract_after = [], [], None

    def is_user_in_blacklist(self, username):
        return username in self.blacklist

    def check_user_was_interacted(self, username):
        when = self.interacted.get(username)
        return (when is not None, when)

    def can_be_reinteract(self, when, hours):
        self.reinteract_after = hours
        return self.reinteract

    def get_following_status(self, username):
        return FollowingStatus.NONE

    def add_interacted_user(self, username, **fields):
        self.added.append((username, fields))

    def enqueue_pending_reply(self, username, **fields):
        self.queued.append((username, fields))


def _ctx(store, interaction=None, follow_limit=lambda: False):
    return SourceContext(
        device="dev",
        args=SimpleNamespace(can_reinteract_after="48"),
        session_state=SimpleNamespace(id="session-1"),
        resource_id=None,
        storage=store,
        profile_filter=None,
        current_job="blogger-followers",
        source="@club",
        on_interaction=lambda **kw: ("on_interaction", kw),
        interaction=interaction or (lambda device, **kw: (True, False, False, False, False, 1, 0, 0)),
        is_follow_limit_reached=follow_limit,
        percentages=Percentages(0, 100, 0, 0, 0, 50),
    )


@pytest.fixture(autouse=True)
def _utils_args(monkeypatch):
    monkeypatch.setattr(utils, "args", SimpleNamespace(), raising=False)


def test_blacklisted_user_is_skipped():
    handler = SourceHandler(_ctx(FakeStore(blacklist={"bad"})))
    assert handler.is_blacklisted("bad")
    assert not handler.is_blacklisted("good")


def test_never_interacted_is_none():
    assert SourceHandler(_ctx(FakeStore())).may_interact_again("new") is None


@pytest.mark.parametrize("reinteract", [True, False])
def test_interacted_user_follows_can_reinteract_after(reinteract):
    store = FakeStore(interacted={"old": datetime(2026, 9, 1, 12, 0)}, reinteract=reinteract)
    assert SourceHandler(_ctx(store)).may_interact_again("old") is reinteract
    assert store.reinteract_after == 48


def test_interacted_too_recently_must_not_count_as_new():
    """The bug caught while writing 7c: `is not False` keeps recent users skipped."""
    store = FakeStore(interacted={"old": datetime(2026, 9, 1, 12, 0)}, reinteract=False)
    assert (SourceHandler(_ctx(store)).may_interact_again("old") is not False) is False


def test_interact_with_records_the_user_under_the_source():
    calls = []

    def interaction(device, **kw):
        calls.append((device, kw))
        kw["greeting_sink"].update(stage="greeted", first_name="Ana")
        return (True, False, False, False, True, 2, 1, 0)

    store = FakeStore()
    result = SourceHandler(_ctx(store, interaction)).interact_with("ana")

    device, kw = calls[0]
    assert device == "dev"
    assert (kw["username"], kw["target"], kw["current_job"], kw["can_follow"]) == (
        "ana", "@club", "blogger-followers", True,
    )
    assert store.added == [(
        "ana",
        dict(session_id="session-1", job_name="blogger-followers", target="@club",
             followed=False, is_requested=False, scraped=False,
             liked=2, watched=1, commented=0, pm_sent=True),
    )]
    assert store.queued == [("ana", {"stage": "greeted", "first_name": "Ana"})]
    assert result == ("on_interaction", {"succeed": True, "followed": False, "scraped": False})


def test_interact_with_explicit_target_and_no_follow_limit():
    calls = []

    def interaction(device, **kw):
        calls.append(kw)
        return (False, False, False, False, False, 0, 0, 0)

    store = FakeStore()
    SourceHandler(_ctx(store, interaction, follow_limit=None)).interact_with("bob", target="bob")
    assert calls[0]["target"] == "bob" and calls[0]["can_follow"] is False
    assert store.added[0][1]["target"] == "bob"
    assert store.queued == []
