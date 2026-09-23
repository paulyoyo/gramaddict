from types import SimpleNamespace

import pytest

from GramAddict.core import utils
from GramAddict.core.interaction import interact_with_user
from GramAddict.core.source_context import build_source_context, follow_limit_checker


def _args(**overrides):
    base = dict(
        app_id="com.instagram.android",
        current_likes_limit=100,
        interactions_count="70",
        stories_count="1",
        stories_percentage="40",
        likes_percentage="100",
        follow_percentage="30",
        comment_percentage="0",
        interact_percentage="50",
        pm_percentage="10",
        likes_count="2",
        scrape_to_file=None,
        follow_limit=None,
        speed_multiplier=1,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _plugin(args):
    session_state = SimpleNamespace(my_username="me", totalFollowed={})
    return SimpleNamespace(
        args=args,
        sessions=[session_state],
        session_state=session_state,
        current_mode="blogger-followers",
    )


@pytest.fixture(autouse=True)
def _utils_args(monkeypatch):
    # get_value logs through utils' module-level args
    monkeypatch.setattr(utils, "args", _args(), raising=False)


def test_context_binds_the_same_interaction_the_plugins_built():
    args = _args()
    plugin = _plugin(args)
    ctx = build_source_context(plugin, "dev", "store", "filter", "blogger-followers", "@club")

    assert ctx.interaction.func is interact_with_user
    assert ctx.interaction.keywords == dict(
        my_username="me",
        likes_count="2",
        likes_percentage=100,
        stories_percentage=40,
        follow_percentage=30,
        comment_percentage=0,
        pm_percentage=10,
        profile_filter="filter",
        args=args,
        session_state=plugin.session_state,
        scraping_file=None,
        current_mode="blogger-followers",
    )
    assert ctx.percentages.interact == 50
    assert (ctx.device, ctx.storage, ctx.source, ctx.current_job) == (
        "dev",
        "store",
        "@club",
        "blogger-followers",
    )


def test_no_stories_when_stories_count_is_zero():
    ctx = build_source_context(
        _plugin(_args(stories_count="0")), None, None, None, "job", "@club"
    )
    assert ctx.percentages.stories == 0


def test_follow_limit_is_counted_per_source():
    session_state = SimpleNamespace(totalFollowed={"@club": 3})
    args = _args(follow_limit="3")
    assert follow_limit_checker(args, session_state, "@club")()
    assert not follow_limit_checker(args, session_state, "@other")()
    assert not follow_limit_checker(_args(), session_state, "@club")()
