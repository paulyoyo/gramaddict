"""Batch 14: plugins don't stop the bot or lose work on a single failure."""
from types import SimpleNamespace

import pytest

from GramAddict.core import utils
from GramAddict.core.source_context import Percentages, SourceContext
from GramAddict.core.sources import blogger as blogger_mod
from GramAddict.core.sources.blogger import BloggerFromFileHandler
from GramAddict.plugins import interact_blogger, like_from_urls
from tests.fakes import InMemoryStore


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(utils, "args", SimpleNamespace(speed_multiplier=1), raising=False)


# --- interact-from-file keeps the user it was handling when the bot crashes -----

class FakeTabBar:
    def __init__(self, device):
        pass

    def navigateToSearch(self):
        return SimpleNamespace(navigate_to_target=lambda username, job: True)


def _from_file(tmp_path, monkeypatch, names):
    (tmp_path / "users.txt").write_text("".join(f"{n}\n" for n in names))
    store = InMemoryStore()
    store.account_path = str(tmp_path)
    ctx = SourceContext(
        device=SimpleNamespace(back=lambda: None),
        args=SimpleNamespace(delete_interacted_users=True, can_reinteract_after="0"),
        session_state=SimpleNamespace(id="s1"),
        resource_id=None,
        storage=store,
        profile_filter=None,
        current_job="interact-from-file",
        source="users.txt 5",
        on_interaction=lambda **kw: True,
        interaction=None,
        is_follow_limit_reached=None,
        percentages=Percentages(0, 100, 0, 0, 0, 50),
    )
    monkeypatch.setattr(blogger_mod, "TabBarView", FakeTabBar)
    return BloggerFromFileHandler(ctx)


def test_crash_mid_user_keeps_that_user_in_the_file(tmp_path, monkeypatch):
    handler = _from_file(tmp_path, monkeypatch, ["ana", "bob", "cid"])

    def interact_with(username, target=None):
        if username == "bob":
            raise RuntimeError("app crashed")
        return True

    monkeypatch.setattr(handler, "interact_with", interact_with)
    with pytest.raises(RuntimeError):
        handler.run()
    # ana is done; bob was in progress and must stay (it used to be dropped)
    assert (tmp_path / "users.txt").read_text() == "bob\ncid\n"


def test_a_clean_run_removes_every_processed_user(tmp_path, monkeypatch):
    handler = _from_file(tmp_path, monkeypatch, ["ana", "bob"])
    monkeypatch.setattr(handler, "interact_with", lambda username, target=None: True)
    handler.run()
    assert (tmp_path / "users.txt").read_text() == ""


# --- like-from-urls: an unknown media type is "not liked", not a crash ------------

def test_unknown_media_type_does_not_crash_like_from_urls(tmp_path, monkeypatch):
    (tmp_path / "urls.txt").write_text("https://www.instagram.com/p/abc/\n")
    post = SimpleNamespace(_is_post_liked=lambda: (False, None))
    posts = SimpleNamespace(
        _get_media_container=lambda: (None, "?"),
        detect_media_type=lambda desc: (None, 0),
        _post_owner=lambda *a: ("bob", None, None),
    )
    monkeypatch.setattr(like_from_urls, "OpenedPostView", lambda device: post)
    monkeypatch.setattr(like_from_urls, "PostsViewList", lambda device: posts)
    monkeypatch.setattr(like_from_urls, "open_instagram_with_url", lambda url: True)
    liked = []
    monkeypatch.setattr(like_from_urls, "register_like", lambda *a: liked.append(1))

    plugin = like_from_urls.LikeFromURLs()
    plugin.device = SimpleNamespace(back=lambda: None)
    plugin.args = SimpleNamespace(delete_interacted_users=False)
    plugin.session_state = SimpleNamespace(id="s1")
    plugin.current_mode = "like-from-urls"
    store = InMemoryStore()
    store.account_path = str(tmp_path)

    plugin.process_file("urls.txt", store)  # used to raise NameError: like_succeed
    assert liked == [] and store.interacted_users == {}


# --- interact-from-file / unfollow-from-file run under run_safely ----------------

def test_file_jobs_are_wrapped_in_run_safely(monkeypatch):
    wrapped = []

    def fake_run_safely(**kw):
        def decorator(func):
            wrapped.append(func.__name__)
            return func

        return decorator

    monkeypatch.setattr(interact_blogger, "run_safely", fake_run_safely)
    monkeypatch.setattr(interact_blogger, "build_source_context", lambda *a: "ctx")
    ran = []
    plugin = interact_blogger.InteractBloggerPostLikers()
    monkeypatch.setattr(plugin, "handle_blogger_from_file", lambda ctx: ran.append(ctx))

    session_state = SimpleNamespace(
        check_limit=lambda **kw: (False, False, False), Limit=SimpleNamespace(ALL="all")
    )
    configs = SimpleNamespace(
        args=SimpleNamespace(
            device=None, interact_from_file=["users.txt 5"], truncate_sources="0",
            screen_record=False,
        )
    )
    plugin.run("dev", configs, "store", [session_state], "filter", "interact-from-file")
    assert "job_file" in wrapped and ran == ["ctx"]
