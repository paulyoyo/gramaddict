import re


def _normalize(text):
    return re.sub(r"[\W\d_]+", " ", text.lower())


def _matches_bio(word, fullname, biography):
    """Mirror of filter.py name/bio scan: word-boundary over normalized text."""
    name_and_bio = _normalize(f"{fullname} {biography}")
    return (
        re.compile(r"\b({0})\b".format(word), flags=re.IGNORECASE).search(name_and_bio)
        is not None
    )


def _matches_handle(word, username):
    """Mirror of filter.py is_handler_blacklisted: substring anywhere."""
    return word.lower() in username.lower()


def test_dj_in_display_name_is_caught():
    # The original bug: "DJ" lives in the display name, not the bio.
    assert _matches_bio("dj", "DJ Carlos", "bookings below 🔥")
    assert _matches_bio("dj", "Carlos DJ", "")


def test_no_false_positive_on_substring_in_bio():
    # word boundary must not match "dj" inside another prose word
    assert not _matches_bio("dj", "Adjani", "adjust your mindset")


def test_still_matches_in_bio():
    assert _matches_bio("sex", "Carlos", "sex coach")


# gap 2: digits/separators glued to the word in name or bio
def test_dj_glued_to_digits_or_separator():
    assert _matches_bio("dj", "DJ2024", "")
    assert _matches_bio("dj", "carlos_dj_music", "")


# gap 1: "dj" anywhere in the username handle
def test_dj_anywhere_in_handle():
    assert _matches_handle("dj", "djcarlos")       # prefix (already worked)
    assert _matches_handle("dj", "carlosdj")       # suffix (already worked)
    assert _matches_handle("dj", "carlos_dj_music")  # middle with separators
    assert _matches_handle("dj", "thedjmusic")     # glued middle


if __name__ == "__main__":
    test_dj_in_display_name_is_caught()
    test_no_false_positive_on_substring_in_bio()
    test_still_matches_in_bio()
    test_dj_glued_to_digits_or_separator()
    test_dj_anywhere_in_handle()
    print("ok")
