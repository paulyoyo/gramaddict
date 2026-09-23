import pytest

from GramAddict.core import navigation
from GramAddict.core.navigation import LanguageNotEnglishError, check_if_english


def _labels(monkeypatch, texts):
    class FakeProfileView:
        def __init__(self, device, is_own_profile=False):
            pass

        def _getSomeText(self):
            return texts

    monkeypatch.setattr(navigation, "ProfileView", FakeProfileView)


def test_english_profile_passes(monkeypatch):
    _labels(monkeypatch, ("posts", "followers", "following"))
    check_if_english(device=None)


def test_non_english_raises_instead_of_exiting(monkeypatch):
    _labels(monkeypatch, ("publicaciones", "seguidores", "seguidos"))
    with pytest.raises(LanguageNotEnglishError):
        check_if_english(device=None)


def test_unreadable_labels_only_warn(monkeypatch):
    _labels(monkeypatch, (None, None, None))
    check_if_english(device=None)
