"""blacklist_words, through the real Filter (name + bio scan and handle scan)."""
import pytest

from GramAddict.core.filter import SkipReason
from tests.profiles import check, make_filter

DJ = {"blacklist_words": ["dj"]}


def _name_or_bio_hit(monkeypatch, word, fullname, biography):
    skipped, reason = check({"blacklist_words": [word]}, monkeypatch, fullname=fullname, biography=biography)
    return skipped and reason == SkipReason.BLACKLISTED_WORD


@pytest.mark.parametrize("fullname", ["DJ Carlos", "Carlos DJ"])
def test_dj_in_display_name_is_caught(monkeypatch, fullname):
    # The original bug: "DJ" lives in the display name, not the bio.
    assert _name_or_bio_hit(monkeypatch, "dj", fullname, "bookings below 🔥")


def test_no_false_positive_on_substring_in_bio(monkeypatch):
    # word boundary must not match "dj" inside another prose word
    assert not _name_or_bio_hit(monkeypatch, "dj", "Adjani", "adjust your mindset")


def test_still_matches_in_bio(monkeypatch):
    assert _name_or_bio_hit(monkeypatch, "sex", "Carlos", "sex coach")


@pytest.mark.parametrize("fullname", ["DJ2024", "carlos_dj_music"])
def test_dj_glued_to_digits_or_separator(monkeypatch, fullname):
    assert _name_or_bio_hit(monkeypatch, "dj", fullname, "music")


@pytest.mark.parametrize("handle", ["djcarlos", "carlosdj", "carlos_dj_music", "thedjmusic"])
def test_dj_anywhere_in_handle(handle):
    assert make_filter(DJ).is_handler_blacklisted(handle)


def test_clean_handle_and_no_words_configured():
    assert not make_filter(DJ).is_handler_blacklisted("carlos.music")
    assert not make_filter({}).is_handler_blacklisted("djcarlos")
    assert not make_filter(None).is_handler_blacklisted("djcarlos")
