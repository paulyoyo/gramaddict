from GramAddict.core.scroll_end_detector import ScrollEndDetector


def _page(detector, usernames):
    detector.notify_new_page()
    for u in usernames:
        detector.notify_username_iterated(u)


def test_detectors_do_not_share_pages():
    first = ScrollEndDetector(repeats_to_end=2)
    _page(first, ["a", "b"])
    _page(first, ["a", "b"])
    assert first.is_the_end()

    second = ScrollEndDetector(repeats_to_end=2)
    _page(second, ["c", "d"])
    assert second.pages == [["c", "d"]]
    assert not second.is_the_end()


def test_detectors_do_not_share_counters():
    first = ScrollEndDetector(skipped_list_limit=1)
    first.notify_skipped_all()
    assert first.is_skipped_limit_reached()
    assert ScrollEndDetector(skipped_list_limit=1).skipped_all == 0
