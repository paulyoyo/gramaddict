"""Every interact plugin hands its SourceContext to handle_sources with the
right arguments (batch 7b). The real handlers need a phone, so they are
replaced by recorders that check the call against the real signature."""
import inspect
from types import SimpleNamespace

import pytest

from GramAddict.core import handle_sources, utils
from GramAddict.core.source_context import Percentages, SourceContext
from GramAddict.core.scroll_end_detector import ScrollEndDetector

ARGS = SimpleNamespace(
    skipped_list_limit="15",
    fling_when_skipped="0",
    scrape_to_file=None,
    likers_limit_per_post="10",
    commenters_limit_per_post="5",
    interact_likers=True,
    interact_commenters=True,
    follow_limit=None,
    speed_multiplier=1,
)


def _ctx():
    return SourceContext(
        device="dev", args=ARGS, session_state=SimpleNamespace(), resource_id=None,
        storage="store", profile_filter="filter", current_job="job", source="@src",
        on_interaction="on", interaction="interaction",
        is_follow_limit_reached=lambda: False,
        percentages=Percentages(0, 100, 0, 0, 0, 50),
    )


@pytest.fixture(autouse=True)
def _utils_args(monkeypatch):
    monkeypatch.setattr(utils, "args", ARGS, raising=False)


def _record(monkeypatch, module, name):
    calls = []
    real = getattr(handle_sources, name)

    def recorder(*args, **kwargs):
        inspect.signature(real).bind(*args, **kwargs)  # raises on a wrong call
        calls.append(args)

    monkeypatch.setattr(module, name, recorder)
    return calls


def _plugin(module, cls_name):
    plugin = getattr(module, cls_name)()
    plugin.args = ARGS
    return plugin


@pytest.mark.parametrize(
    "module_name, cls_name, method, handler, detector",
    [
        ("interact_blogger_followers", "InteractBloggerFollowers_Following", "handle_blogger", "handle_followers", True),
        ("interact_blogger_post_likers", "InteractBloggerPostLikers", "handle_blogger", "handle_likers", True),
        ("interact_hashtag_likers", "InteractHashtagLikers", "handle_hashtag", "handle_likers", True),
        ("interact_place_likers", "InteractPlaceLikers", "handle_place", "handle_likers", True),
        ("interact_hashtag_posts", "InteractHashtagPosts", "handle_hashtag", "handle_posts", False),
        ("interact_place_posts", "InteractPlacePosts", "handle_place", "handle_posts", False),
        ("interact_blogger", "InteractBloggerPostLikers", "handle_blogger", "handle_blogger", False),
        ("interact_blogger", "InteractBloggerPostLikers", "handle_blogger_from_file", "handle_blogger_from_file", False),
    ],
)
def test_plugin_passes_ctx(monkeypatch, module_name, cls_name, method, handler, detector):
    module = __import__(f"GramAddict.plugins.{module_name}", fromlist=[cls_name])
    calls = _record(monkeypatch, module, handler)
    ctx = _ctx()
    getattr(_plugin(module, cls_name), method)(ctx)
    assert len(calls) == 1 and calls[0][0] is ctx
    if detector:
        assert isinstance(calls[0][1], ScrollEndDetector)


def test_feed_passes_ctx_without_follow_limit(monkeypatch):
    from GramAddict.plugins import interact_feed

    calls = _record(monkeypatch, interact_feed, "handle_posts")
    ctx = _ctx()
    _plugin(interact_feed, "InteractOwnFeed").handle_feed(ctx)
    passed = calls[0][0]
    assert passed.is_follow_limit_reached is None
    assert passed.source == "@src" and ctx.is_follow_limit_reached is not None


def test_urls_plugin_uses_the_post_as_source(monkeypatch):
    from GramAddict.plugins import interact_post_likers_commenters_from_urls as m

    likers = _record(monkeypatch, m, "handle_likers_from_post")
    commenters = _record(monkeypatch, m, "handle_commenters")
    monkeypatch.setattr(m, "open_instagram_with_url", lambda url: True)
    monkeypatch.setattr(
        m.PostsViewList, "_find_likers_container", lambda self: (True, 50)
    )
    plugin = _plugin(m, "InteractPostLikersCommentersFromURLs")
    plugin.session_state = SimpleNamespace(totalFollowed={})
    plugin.device = SimpleNamespace(back=lambda: None)
    plugin.profile_filter = SimpleNamespace(is_num_likers_in_range=lambda n: True)

    url = "https://www.instagram.com/p/abc/"
    plugin.process_single_post(url, _ctx())

    for calls in (likers, commenters):
        post_ctx = calls[0][0]
        assert post_ctx.source == url
        assert post_ctx.current_job == "post-likers-commenters-from-file"
        assert post_ctx.on_interaction == "on"
