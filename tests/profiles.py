"""A complete fake profile for Filter.check_profile, and a Filter without disk."""
from types import SimpleNamespace

from GramAddict.core.filter import Filter
from GramAddict.core.views import FollowStatus


class RecordingStore:
    def __init__(self):
        self.reasons = []

    def add_filter_user(self, username, profile_data, skip_reason):
        self.reasons.append(skip_reason)


def make_filter(conditions):
    f = Filter.__new__(Filter)
    f.conditions = conditions
    f.storage = RecordingStore()
    return f


def full_profile(**overrides):
    """Passes every rule unless a test overrides a field."""
    profile = dict(
        is_restricted=False,
        follow_button_text=FollowStatus.FOLLOW,
        followers=500,
        followings=400,
        posts_count=12,
        is_private=False,
        fullname="Ana Perez",
        biography="music lover and traveller",
        link_in_bio=None,
        has_business_category=False,
        mutual_friends=0,
    )
    profile.update(overrides)
    return SimpleNamespace(**profile)


def check(conditions, monkeypatch, **overrides):
    """Run the real check_profile; returns (skipped, skip_reason)."""
    f = make_filter(conditions)
    profile = full_profile(**overrides)
    monkeypatch.setattr(f, "get_all_data", lambda device: profile)
    _, skipped = f.check_profile(None, "someone")
    return skipped, f.storage.reasons[-1] if f.storage.reasons else None
