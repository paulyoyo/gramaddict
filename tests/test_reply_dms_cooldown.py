from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from GramAddict.core import utils
from GramAddict.plugins.action_reply_dms import COOLDOWN_FILE, ActionReplyDMs


@pytest.fixture(autouse=True)
def _utils_args(monkeypatch):
    monkeypatch.setattr(utils, "args", SimpleNamespace(), raising=False)


def _plugin(cooldown, tmp_path, hours_ago=None):
    plugin = ActionReplyDMs()
    plugin.args = SimpleNamespace(reply_dms_cooldown_hours=cooldown)
    storage = SimpleNamespace(account_path=str(tmp_path))
    if hours_ago is not None:
        last = datetime.now() - timedelta(hours=hours_ago)
        (tmp_path / COOLDOWN_FILE).write_text(last.isoformat())
    return plugin, storage


def test_first_run_is_allowed(tmp_path):
    plugin, storage = _plugin("20-28", tmp_path)
    assert plugin._can_run(storage)


def test_default_cooldown_blocks_a_second_run_the_same_day(tmp_path):
    plugin, storage = _plugin("20-28", tmp_path, hours_ago=5)
    assert not plugin._can_run(storage)


def test_short_cooldown_allows_a_run_a_few_hours_later(tmp_path):
    plugin, storage = _plugin("2-4", tmp_path, hours_ago=5)
    assert plugin._can_run(storage)
    plugin, storage = _plugin("2-4", tmp_path, hours_ago=1)
    assert not plugin._can_run(storage)


def test_default_is_the_old_daily_window():
    arg = next(
        a for a in ActionReplyDMs().arguments if a["arg"] == "--reply-dms-cooldown-hours"
    )
    assert arg["default"] == "20-28"


def test_reply_dms_runs_before_outreach_jobs():
    from GramAddict.core.bot_flow import reply_dms_first

    jobs = ["blogger-followers", "reply-dms", "blogger-post-likers"]
    assert reply_dms_first(jobs) == ["reply-dms", "blogger-followers", "blogger-post-likers"]
    assert reply_dms_first(["blogger-followers"]) == ["blogger-followers"]


# Bounds from a real IG v300 thread dump (720px wide): our greeting, then "Si bro".
GREETING = ("Holi Stick! Vi que sigues a @miabotanicclub.pe", 704)
SI_BRO = ("Si bro", 242)


def test_reply_after_our_greeting_is_read():
    from GramAddict.plugins.action_reply_dms import text_after_our_last_message

    assert text_after_our_last_message([GREETING, SI_BRO], 720) == "Si bro"


def test_our_own_last_message_is_not_a_reply():
    from GramAddict.plugins.action_reply_dms import text_after_our_last_message

    assert text_after_our_last_message([GREETING], 720) is None
    assert text_after_our_last_message([SI_BRO, GREETING], 720) is None
    assert text_after_our_last_message([], 720) is None


def test_several_incoming_bubbles_are_joined_and_long_ones_stay_incoming():
    from GramAddict.plugins.action_reply_dms import text_after_our_last_message

    long_incoming = ("Hola! si claro pasame el link porfa", 609)
    assert (
        text_after_our_last_message([GREETING, SI_BRO, long_incoming], 720)
        == "Si bro / Hola! si claro pasame el link porfa"
    )


@pytest.mark.parametrize(
    "text",
    ["👍", "👍🏽", "Si bro", "sí", "Dale!", "claro 🔥", "si bro 🔥🔥", "❤️", "ok", "Siii 🙌"],
)
def test_obvious_yes(text):
    from GramAddict.plugins.action_reply_dms import is_obvious_yes

    assert is_obvious_yes(text)


@pytest.mark.parametrize(
    "text",
    ["", None, "no", "no gracias", "bro", "quien eres?", "si pero luego", "👎", "🤔", "ya lo escuché"],
)
def test_not_obvious_yes(text):
    from GramAddict.plugins.action_reply_dms import is_obvious_yes

    assert not is_obvious_yes(text)


class _Store:
    def __init__(self, entry):
        self.entries = [entry]

    def update_pending_reply(self, username, **fields):
        self.entries[0].update(fields)

    def remove_pending_reply(self, username):
        self.entries = []


def test_unreachable_user_is_dropped_after_three_visits():
    entry = {"username": "privada"}
    store = _Store(entry)
    plugin = ActionReplyDMs()
    plugin._count_unreachable(store, entry)
    plugin._count_unreachable(store, entry)
    assert store.entries and entry["unreachable"] == 2
    plugin._count_unreachable(store, entry)
    assert store.entries == []
