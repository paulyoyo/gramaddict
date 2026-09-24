import pytest

from GramAddict.core.filter import SkipReason
from tests.profiles import check, make_filter


def test_a_profile_that_passes_every_rule_is_not_skipped(monkeypatch):
    assert check({"min_followers": 100, "blacklist_words": ["dj"]}, monkeypatch) == (False, None)


@pytest.mark.parametrize(
    "conditions, overrides, reason",
    [
        ({"skip_if_public": True}, dict(is_private=False), SkipReason.IS_PUBLIC),
        ({"skip_if_private": True}, dict(is_private=True), SkipReason.IS_PRIVATE),
        ({}, dict(is_private=None), SkipReason.UNKNOWN_PRIVACY),
        ({"min_followers": 1000}, {}, SkipReason.LT_FOLLOWERS),
        ({"max_followers": 100}, {}, SkipReason.GT_FOLLOWERS),
        ({"min_followings": 1000}, {}, SkipReason.LT_FOLLOWINGS),
        ({"max_followings": 100}, {}, SkipReason.GT_FOLLOWINGS),
        ({"min_potency_ratio": 2}, {}, SkipReason.POTENCY_RATIO),
        ({"mutual_friends": 3}, dict(mutual_friends=1), SkipReason.LT_MUTUAL),
        ({"skip_if_link_in_bio": True}, dict(link_in_bio="linktr.ee/x"), SkipReason.HAS_LINK_IN_BIO),
        ({"skip_business": True}, dict(has_business_category=True), SkipReason.HAS_BUSINESS),
        ({"skip_non_business": True}, {}, SkipReason.HAS_NON_BUSINESS),
        ({"min_posts": 50}, {}, SkipReason.NOT_ENOUGH_POSTS),
        ({"mandatory_words": ["cat"]}, dict(biography=""), SkipReason.BIOGRAPHY_IS_EMPTY),
        ({"blacklist_words": ["music"]}, {}, SkipReason.BLACKLISTED_WORD),
        ({"mandatory_words": ["dogs"]}, {}, SkipReason.MISSING_MANDATORY_WORDS),
    ],
)
def test_each_rule_skips_with_its_reason(monkeypatch, conditions, overrides, reason):
    assert check(conditions, monkeypatch, **overrides) == (True, reason)


@pytest.mark.parametrize("is_private", [True, False])
def test_skip_if_public_keeps_private_and_unknown_is_its_own_reason(monkeypatch, is_private):
    skipped, reason = check({"skip_if_public": True}, monkeypatch, is_private=is_private)
    assert skipped is (not is_private)


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
    assert make_filter(conditions).can_pm_to_private_or_empty() is expected
