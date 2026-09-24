import inspect
import os
from types import SimpleNamespace

import pytest

from GramAddict.core import utils
from GramAddict.core.source_context import Percentages, SourceContext
from GramAddict.core.sources.base import SourceHandler
from GramAddict.core.storage import FollowingStatus, InteractionStore, Storage
from tests.fakes import InMemoryStore

PROTOCOL_METHODS = [
    name
    for name, member in vars(InteractionStore).items()
    if inspect.isfunction(member) and not name.startswith("_")
]


@pytest.fixture(autouse=True)
def _utils_args(monkeypatch):
    monkeypatch.setattr(utils, "args", SimpleNamespace(), raising=False)


def test_protocol_lists_what_the_bot_uses():
    assert len(PROTOCOL_METHODS) == 17


def test_real_storage_satisfies_the_protocol(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert isinstance(Storage("me"), InteractionStore)
    for name in PROTOCOL_METHODS:
        assert callable(getattr(Storage, name)), name


def test_in_memory_store_satisfies_it_and_never_writes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = InMemoryStore()
    assert isinstance(store, InteractionStore)
    store.add_interacted_user("ana", session_id="s1", followed=True)
    store.enqueue_pending_reply("ana", stage="greeted")
    store.save_source_position("@club", "blogger-followers", 12)
    assert os.listdir(tmp_path) == []
    assert store.get_following_status("ana") == FollowingStatus.FOLLOWED
    assert store.get_following_status("bob") == FollowingStatus.NOT_IN_LIST
    assert store.get_pending_replies()[0]["username"] == "ana"
    assert store.get_source_position("@club", "blogger-followers") == 12


def _ctx(store, can_reinteract_after):
    return SourceContext(
        device="dev",
        args=SimpleNamespace(can_reinteract_after=can_reinteract_after),
        session_state=SimpleNamespace(id="s1"),
        resource_id=None,
        storage=store,
        profile_filter=None,
        current_job="blogger-followers",
        source="@club",
        on_interaction=lambda **kw: True,
        interaction=lambda device, **kw: (True, False, False, False, False, 1, 0, 0),
        is_follow_limit_reached=lambda: False,
        percentages=Percentages(0, 100, 0, 0, 0, 50),
    )


def test_a_user_we_just_interacted_with_is_skipped_until_reinteract_after():
    store = InMemoryStore(blacklist=["spam"])
    handler = SourceHandler(_ctx(store, can_reinteract_after="48"))

    assert handler.is_blacklisted("spam")
    assert handler.may_interact_again("ana") is None  # new user
    assert handler.interact_with("ana")
    assert handler.may_interact_again("ana") is False  # just now: skip
    assert store.interacted_users["ana"]["target"] == "@club"

    # can-reinteract-after 0 means "always"
    assert SourceHandler(_ctx(store, can_reinteract_after="0")).may_interact_again("ana") is True
