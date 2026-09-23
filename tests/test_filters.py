from types import SimpleNamespace

import pytest

from GramAddict.core.filter import Filter, SkipReason


class _Storage:
    def __init__(self):
        self.reasons = []

    def add_filter_user(self, username, profile_data, skip_reason):
        self.reasons.append(skip_reason)


def _filter(conditions):
    f = Filter.__new__(Filter)
    f.conditions = conditions
    f.storage = _Storage()
    return f


def _check(conditions, is_private, monkeypatch):
    f = _filter(conditions)
    profile = SimpleNamespace(
        is_restricted=False,
        follow_button_text="Follow",
        followers=100,
        followings=100,
        posts_count=10,
        is_private=is_private,
    )
    monkeypatch.setattr(f, "get_all_data", lambda device: profile)
    try:
        f.check_profile(None, "someone")
    except AttributeError:
        pass  # later checks need more profile fields; we only assert the privacy step
    return f.storage.reasons


def test_skip_if_public_skips_public(monkeypatch):
    assert _check({"skip_if_public": True}, False, monkeypatch) == [
        SkipReason.IS_PUBLIC
    ]


def test_skip_if_public_keeps_private(monkeypatch):
    reasons = _check({"skip_if_public": True}, True, monkeypatch)
    assert SkipReason.IS_PUBLIC not in reasons
    assert SkipReason.IS_PRIVATE not in reasons


def test_skip_if_private_skips_private(monkeypatch):
    assert _check({"skip_if_private": True}, True, monkeypatch) == [
        SkipReason.IS_PRIVATE
    ]


def test_skip_if_public_ignores_unknown_privacy(monkeypatch):
    assert SkipReason.IS_PUBLIC not in _check(
        {"skip_if_public": True}, None, monkeypatch
    )


@pytest.mark.parametrize(
    "conditions, expected",
    [
        (None, True),
        ({}, True),
        ({"pm_to_private_or_empty": True}, True),
        ({"pm_to_private_or_empty": False}, False),
    ],
)
def test_pm_to_private_or_empty_defaults_to_true(conditions, expected):
    assert _filter(conditions).can_pm_to_private_or_empty() is expected
