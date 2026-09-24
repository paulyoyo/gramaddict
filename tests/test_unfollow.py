"""Who gets unfollowed, and what is recorded (batch 10)."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from GramAddict.core import utils
from GramAddict.core.resources import ResourceID
from GramAddict.core.storage import FollowingStatus
from GramAddict.plugins import action_unfollow_followers as m
from GramAddict.plugins.action_unfollow_followers import (
    ActionUnfollowFollowers,
    UnfollowResult,
    UnfollowRestriction,
    should_unfollow,
)
from tests.fakes import InMemoryStore

APP = "com.instagram.android"


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(utils, "args", SimpleNamespace(speed_multiplier=1), raising=False)
    monkeypatch.setattr(m, "random_sleep", lambda *a, **k: None)
    monkeypatch.setattr(m, "save_crash", lambda device: None)
    monkeypatch.setattr(m.UniversalActions, "detect_block", staticmethod(lambda device: False))


def _mode_flags(restriction, job_name):
    """The same two flags the plugin passes to do_unfollow."""
    check = restriction in [
        UnfollowRestriction.FOLLOWED_BY_SCRIPT_NON_FOLLOWERS,
        UnfollowRestriction.ANY_NON_FOLLOWERS,
        UnfollowRestriction.ANY_FOLLOWERS,
    ]
    return check, job_name == "unfollow-any-followers"


@pytest.mark.parametrize(
    "restriction, job, follower, non_follower, unknown",
    [
        (UnfollowRestriction.ANY, "unfollow-any", True, True, True),
        (UnfollowRestriction.FOLLOWED_BY_SCRIPT, "unfollow", True, True, True),
        (UnfollowRestriction.FOLLOWED_BY_SCRIPT_NON_FOLLOWERS, "unfollow-non-followers", False, True, False),
        (UnfollowRestriction.ANY_NON_FOLLOWERS, "unfollow-any-non-followers", False, True, False),
        # the bug: any-followers used to unfollow non-followers too
        (UnfollowRestriction.ANY_FOLLOWERS, "unfollow-any-followers", True, False, False),
    ],
)
def test_who_each_mode_unfollows(restriction, job, follower, non_follower, unknown):
    check, followers = _mode_flags(restriction, job)
    assert should_unfollow(check, followers, True) is follower
    assert should_unfollow(check, followers, False) is non_follower
    assert should_unfollow(check, followers, None) is unknown


# --- the profile page -------------------------------------------------------------

class FakeView:
    def __init__(self, present, clicks, name):
        self.present, self.clicks, self.name = present, clicks, name

    def exists(self, *a, **k):
        return self.present

    def click(self, *a, **k):
        self.clicks.append(self.name)

    def scroll(self, *a):
        pass


class FakeProfile:
    """Buttons present on screen: any of following, follow, confirm."""

    def __init__(self, *buttons):
        self.buttons, self.clicks = set(buttons), []
        self.rid = ResourceID(APP)

    def find(self, **kw):
        text = kw.get("textMatches", "")
        if text == m.FOLLOWING_REGEX:
            name = "following"
        elif text == m.NOT_FOLLOWING_REGEX:
            name = "follow"
        elif kw.get("resourceId") == self.rid.FOLLOW_SHEET_UNFOLLOW_ROW:
            name = "confirm"
        else:
            name = "other"
        return FakeView(name in self.buttons, self.clicks, name)


def _plugin():
    plugin = ActionUnfollowFollowers()
    plugin.args = SimpleNamespace(app_id=APP)
    plugin.ResourceID = ResourceID(APP)
    return plugin


@pytest.mark.parametrize(
    "buttons, result, clicks",
    [
        (("following", "confirm"), UnfollowResult.UNFOLLOWED, ["following", "confirm"]),
        (("follow",), UnfollowResult.NOT_FOLLOWING, []),
        ((), UnfollowResult.FAILED, []),  # nothing recognisable on screen
        (("following",), UnfollowResult.FAILED, ["following"]),  # confirm sheet never came
    ],
)
def test_profile_unfollow_outcomes(buttons, result, clicks):
    device = FakeProfile(*buttons)
    assert _plugin().do_unfollow_from_profile(device) == result
    assert device.clicks == clicks


# --- search-based `unfollow` job: what gets recorded -------------------------------

def _store_with_bot_followed(username):
    store = InMemoryStore()
    store.add_interacted_user(username, session_id="old", followed=True)
    long_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S.%f")
    store.interacted_users[username]["last_interaction"] = long_ago
    return store


class FakeTabBar:
    def __init__(self, device):
        pass

    def navigateToSearch(self):
        return SimpleNamespace(navigate_to_target=lambda username, job: True)

    def navigateToHome(self):
        pass


@pytest.mark.parametrize(
    "result, status, counted",
    [
        (UnfollowResult.UNFOLLOWED, FollowingStatus.UNFOLLOWED, 1),
        (UnfollowResult.NOT_FOLLOWING, FollowingStatus.UNFOLLOWED, 0),
        # the bug: a UI failure used to be recorded as UNFOLLOWED, so never retried
        (UnfollowResult.FAILED, FollowingStatus.FOLLOWED, 0),
    ],
)
def test_search_unfollow_records_only_real_outcomes(monkeypatch, result, status, counted):
    monkeypatch.setattr(m, "TabBarView", FakeTabBar)
    plugin = _plugin()
    plugin.args.unfollow_delay = "3"
    plugin.state = SimpleNamespace(is_job_completed=False)
    plugin.session_state = SimpleNamespace(
        id="now", check_limit=lambda **k: False, Limit=SimpleNamespace(UNFOLLOWS="u")
    )
    monkeypatch.setattr(plugin, "do_unfollow_from_profile", lambda device: result)
    store = _store_with_bot_followed("ana")
    unfollows = []

    device = SimpleNamespace(back=lambda: None)
    plugin.unfollow_from_list(device, 5, lambda: unfollows.append(1), store, "me", "unfollow")

    assert store.get_following_status("ana") == status
    assert len(unfollows) == counted
    # a failed one is still eligible next run
    assert ("ana" in store.get_unfollowable_users(3, 5)) is (result == UnfollowResult.FAILED)


# --- do_unfollow: only checks "follows you" when the mode needs it ------------------

def test_any_mode_does_not_check_followers(monkeypatch):
    plugin = _plugin()
    checked = []
    monkeypatch.setattr(plugin, "check_is_follower", lambda *a: checked.append(1) or None)
    monkeypatch.setattr(plugin, "do_unfollow_from_profile", lambda d: UnfollowResult.UNFOLLOWED)
    device = SimpleNamespace(
        find=lambda **kw: SimpleNamespace(exists=lambda *a: True, click_retry=lambda **k: None),
        back=lambda: None,
    )
    assert plugin.do_unfollow(device, "ana", "me", check_if_is_follower=False) is True
    assert checked == []


def test_any_followers_skips_a_non_follower(monkeypatch):
    plugin = _plugin()
    monkeypatch.setattr(plugin, "check_is_follower", lambda *a: False)
    unfollowed = []
    monkeypatch.setattr(plugin, "do_unfollow_from_profile", lambda d: unfollowed.append(1))
    device = SimpleNamespace(
        find=lambda **kw: SimpleNamespace(exists=lambda *a: True, click_retry=lambda **k: None),
        back=lambda: None,
    )
    assert plugin.do_unfollow(device, "ana", "me", True, unfollow_followers=True) is False
    assert unfollowed == []
