"""What the reply job does with each kind of answer (batch 9). Nobody who
replied may be lost: only a clear answer, a delivered Slack alert, or a sent
final link removes a person from the queue."""
from types import SimpleNamespace

import pytest
import requests

from GramAddict.core import deepseek, utils
from GramAddict.core.deepseek import ERROR, NO, UNSURE, YES
from GramAddict.plugins import action_reply_dms as m
from GramAddict.plugins.action_reply_dms import Q_INTERESTED, Q_SOUNDCLOUD, ActionReplyDMs
from tests.fakes import InMemoryStore

CFG = {
    "youtube-link": "https://youtu.be/mix",
    "soundcloud-link": "https://soundcloud.com/mix",
    "youtube-messages": ["YT {link}"],
    "soundcloud-messages": ["SC {link}"],
}


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(utils, "args", SimpleNamespace(), raising=False)


@pytest.fixture
def plugin(monkeypatch):
    p = ActionReplyDMs()
    p.cfg = CFG
    p.slack_webhook = "https://hooks.slack.test/x"
    p.sent = []
    monkeypatch.setattr(p, "_human_reply_pause", lambda target: None)
    monkeypatch.setattr(p, "_send_reply", lambda device, text: p.sent.append(text) or True)
    return p


def _store(stage="greeted"):
    store = InMemoryStore()
    store.enqueue_pending_reply("ana", stage=stage)
    return store


def _answer(monkeypatch, intent):
    monkeypatch.setattr(m, "classify_intent", lambda cfg, q, text: intent)


def _slack(monkeypatch, ok):
    calls = []
    monkeypatch.setattr(m, "slack_send_text", lambda url, text: calls.append(text) or ok)
    return calls


def _queued(store):
    return {e["username"]: e for e in store.get_pending_replies()}


# --- greeted: "want to hear the mix?" ---------------------------------------

def test_yes_sends_youtube_and_waits_for_soundcloud(plugin, monkeypatch):
    _answer(monkeypatch, YES)
    store = _store()
    plugin._handle_greeted(None, store, "ana", "sí dale")
    assert plugin.sent == ["YT https://youtu.be/mix"]
    assert _queued(store)["ana"]["stage"] == "sent_youtube"


def test_failed_youtube_send_keeps_the_person_greeted(plugin, monkeypatch):
    _answer(monkeypatch, YES)
    monkeypatch.setattr(plugin, "_send_reply", lambda device, text: False)
    store = _store()
    plugin._handle_greeted(None, store, "ana", "sí dale")
    assert _queued(store)["ana"]["stage"] == "greeted"


def test_no_drops_the_person(plugin, monkeypatch):
    _answer(monkeypatch, NO)
    store = _store()
    plugin._handle_greeted(None, store, "ana", "no gracias")
    assert "ana" not in _queued(store)


def test_deepseek_error_keeps_the_person_and_alerts_nobody(plugin, monkeypatch):
    _answer(monkeypatch, ERROR)
    slack = _slack(monkeypatch, True)
    store = _store()
    plugin._handle_greeted(None, store, "ana", "mmm quizás")
    assert "ana" in _queued(store) and slack == [] and plugin.sent == []


@pytest.mark.parametrize("slack_ok, kept", [(True, False), (False, True)])
def test_unsure_is_dropped_only_after_slack_got_it(plugin, monkeypatch, slack_ok, kept):
    _answer(monkeypatch, UNSURE)
    slack = _slack(monkeypatch, slack_ok)
    store = _store()
    plugin._handle_greeted(None, store, "ana", "quién eres?")
    assert len(slack) == 1 and "@ana" in slack[0]
    assert ("ana" in _queued(store)) is kept


def test_unsure_without_slack_keeps_the_person(plugin, monkeypatch):
    _answer(monkeypatch, UNSURE)
    slack = _slack(monkeypatch, True)
    plugin.slack_webhook = None
    store = _store()
    plugin._handle_greeted(None, store, "ana", "quién eres?")
    assert "ana" in _queued(store) and slack == []


# --- sent_youtube: "do you use SoundCloud?" -----------------------------------

def test_soundcloud_yes_sends_the_link_and_waits_for_a_thanks(plugin, monkeypatch):
    _answer(monkeypatch, YES)
    store = _store("sent_youtube")
    plugin._handle_sent_youtube(None, store, "ana", "sí uso soundcloud")
    assert plugin.sent == ["SC https://soundcloud.com/mix"]
    assert _queued(store)["ana"]["stage"] == "sent_soundcloud"


# --- courtesy: "gracias", "qué chévere" ---------------------------------------


def _courtesy(monkeypatch, main):
    """The stage question answers `main`; the courtesy question answers YES."""
    monkeypatch.setattr(
        m, "classify_intent", lambda cfg, q, text: YES if q == m.Q_COURTESY else main
    )


def test_thanks_after_greeting_is_thanked_back_and_kept(plugin, monkeypatch):
    _courtesy(monkeypatch, NO)
    plugin.cfg = {**CFG, "thanks-messages": ["Gracias a ti!"]}
    store = _store("greeted")
    plugin._handle_greeted(None, store, "ana", "gracias por escribir")
    assert plugin.sent == ["Gracias a ti!"]
    assert _queued(store)["ana"]["stage"] == "greeted"
    assert _queued(store)["ana"]["thanked"] == "greeted"


def test_thanks_after_youtube_also_asks_about_soundcloud(plugin, monkeypatch):
    _courtesy(monkeypatch, NO)
    plugin.cfg = {**CFG, "thanks-messages": ["Gracias!"], "soundcloud-question": ["Usas SC?"]}
    store = _store("sent_youtube")
    plugin._handle_sent_youtube(None, store, "ana", "gracias 🔥")
    assert plugin.sent == ["Gracias! Usas SC?"]
    assert _queued(store)["ana"]["stage"] == "sent_youtube"


def test_second_courtesy_in_a_stage_ends_without_another_thanks(plugin, monkeypatch):
    _courtesy(monkeypatch, UNSURE)
    store = _store("sent_youtube")
    store.update_pending_reply("ana", thanked="sent_youtube")
    plugin._handle_sent_youtube(None, store, "ana", "gracias de nuevo")
    assert plugin.sent == []
    assert "ana" not in _queued(store)


def test_thanks_after_soundcloud_is_thanked_once_and_done(plugin, monkeypatch):
    _courtesy(monkeypatch, NO)
    store = _store("sent_soundcloud")
    plugin._handle_sent_soundcloud(None, store, "ana", "buenazo, gracias!")
    assert plugin.sent == [m.DEFAULT_THANKS]
    assert "ana" not in _queued(store)


def test_other_reply_after_soundcloud_goes_to_slack(plugin, monkeypatch):
    _answer(monkeypatch, NO)
    calls = _slack(monkeypatch, ok=True)
    store = _store("sent_soundcloud")
    plugin._handle_sent_soundcloud(None, store, "ana", "cuándo tocas en Lima?")
    assert plugin.sent == [] and len(calls) == 1
    assert "ana" not in _queued(store)


def test_courtesy_check_failing_never_drops_a_no(plugin, monkeypatch):
    monkeypatch.setattr(
        m, "classify_intent", lambda cfg, q, text: ERROR if q == m.Q_COURTESY else NO
    )
    store = _store("greeted")
    plugin._handle_greeted(None, store, "ana", "gracias")
    assert plugin.sent == [] and "ana" in _queued(store)


def test_after_soundcloud_only_unread_threads_are_checked_and_silence_expires(
    plugin, monkeypatch, tmp_path
):
    old = "2020-01-01 00:00:00.000000"
    store = InMemoryStore()
    store.account_path = str(tmp_path)
    store.enqueue_pending_reply("silent_old", stage="sent_soundcloud", sent_at=old)
    store.enqueue_pending_reply("replied_old", stage="sent_soundcloud", sent_at=old, full_name="Replied Old")
    store.enqueue_pending_reply("silent_new", stage="sent_soundcloud")
    store.enqueue_pending_reply("waiting", stage="greeted", sent_at=old)
    plugin.args = SimpleNamespace(
        app_id="com.instagram.android", username="me", reply_dms_cooldown_hours="0",
        reply_dms_min_hours="0", reply_dms_limit="10",
    )
    monkeypatch.setattr(m, "load_deepseek_config", lambda u: CFG)
    monkeypatch.setattr(m, "load_slack_config", lambda u: None)
    monkeypatch.setattr(plugin, "_scan_inbox", lambda device: [("Replied Old", None)])
    checked = []
    monkeypatch.setattr(plugin, "_process_user", lambda d, s, entry, p: checked.append(entry["username"]))
    plugin.run(None, SimpleNamespace(args=plugin.args), store, None, None, "reply-dms")

    assert sorted(checked) == ["replied_old", "waiting"]  # silent_new isn't opened
    assert "silent_old" not in _queued(store)  # 72 h of silence: done
    assert "replied_old" in _queued(store)  # replied late: never expired


def test_failed_soundcloud_send_keeps_the_person(plugin, monkeypatch):
    _answer(monkeypatch, YES)
    monkeypatch.setattr(plugin, "_send_reply", lambda device, text: False)
    store = _store("sent_youtube")
    plugin._handle_sent_youtube(None, store, "ana", "sí")
    assert _queued(store)["ana"]["stage"] == "sent_youtube"


def test_bare_emoji_is_not_a_soundcloud_yes(plugin, monkeypatch):
    asked = []
    monkeypatch.setattr(m, "classify_intent", lambda cfg, q, text: asked.append(q) or UNSURE)
    assert plugin._classify(Q_SOUNDCLOUD, "🔥🔥") == UNSURE
    assert asked == [Q_SOUNDCLOUD]
    # ...but it still is to the mix question, and words still count on both
    assert plugin._classify(Q_INTERESTED, "🔥🔥") == YES
    assert plugin._classify(Q_SOUNDCLOUD, "si 🔥") == YES


def test_yes_replies_from_config_skip_deepseek(plugin, monkeypatch):
    monkeypatch.setattr(m, "classify_intent", lambda cfg, q, text: UNSURE)
    plugin.cfg = {**CFG, "yes-replies": ["de una", "sale pe", "🫡"]}
    assert plugin._classify(Q_INTERESTED, "De una!!") == YES
    assert plugin._classify(Q_SOUNDCLOUD, "sale pe") == YES
    assert plugin._classify(Q_INTERESTED, "🫡") == YES
    assert plugin._classify(Q_SOUNDCLOUD, "🫡") == UNSURE  # bare emoji rule still applies
    # the whole reply must match: a known phrase inside a longer reply goes to DeepSeek
    assert plugin._classify(Q_INTERESTED, "de una pero mañana") == UNSURE


# --- run(): an aborted round doesn't start the cooldown ------------------------

def test_aborted_round_does_not_record_the_cooldown(plugin, monkeypatch, tmp_path):
    store = _store()
    store.account_path = str(tmp_path)
    plugin.args = SimpleNamespace(
        app_id="com.instagram.android", username="me", reply_dms_cooldown_hours="0",
        reply_dms_min_hours="0", reply_dms_limit="10",
    )
    monkeypatch.setattr(m, "load_deepseek_config", lambda u: CFG)
    monkeypatch.setattr(m, "load_slack_config", lambda u: None)
    monkeypatch.setattr(plugin, "_scan_inbox", lambda device: [])

    def crash(*a):
        raise m.DeviceFacade.AppHasCrashed()

    monkeypatch.setattr(plugin, "_process_user", crash)
    monkeypatch.setattr(m, "open_instagram", lambda device: False)
    configs = SimpleNamespace(args=plugin.args)
    plugin.run(None, configs, store, None, None, "reply-dms")
    assert not (tmp_path / m.COOLDOWN_FILE).exists()

    monkeypatch.setattr(plugin, "_process_user", lambda *a: None)
    plugin.run(None, configs, store, None, None, "reply-dms")
    assert (tmp_path / m.COOLDOWN_FILE).exists()


# --- DeepSeek client ------------------------------------------------------------

@pytest.mark.parametrize(
    "content, expected",
    [("YES", YES), ("Yes.", YES), ("NO", NO), ("no", NO), ("UNSURE", UNSURE),
     ("NOT SURE", UNSURE), ("NONE", UNSURE), ("", UNSURE), ("Maybe", UNSURE)],
)
def test_parse_answer_reads_whole_words(content, expected):
    assert deepseek.parse_answer(content) == expected


class _Resp:
    def __init__(self, status, content="YES"):
        self.status_code = status
        self._content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


def _deepseek_calls(monkeypatch, responses):
    calls = []

    def post(*a, **k):
        calls.append(1)
        r = responses[min(len(calls), len(responses)) - 1]
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(deepseek.requests, "post", post)
    monkeypatch.setattr(deepseek, "sleep", lambda s: None)
    return calls


def test_retries_rate_limits_and_timeouts_then_answers(monkeypatch):
    calls = _deepseek_calls(monkeypatch, [_Resp(429), requests.Timeout("slow"), _Resp(200, "NO")])
    assert deepseek.classify_intent({"deepseek-api-key": "k"}, "q", "no") == NO
    assert len(calls) == 3


def test_gives_up_with_error_not_unsure(monkeypatch):
    calls = _deepseek_calls(monkeypatch, [_Resp(503)])
    assert deepseek.classify_intent({"deepseek-api-key": "k"}, "q", "x") == ERROR
    assert len(calls) == deepseek.ATTEMPTS


def test_client_errors_and_missing_key_are_not_retried(monkeypatch):
    calls = _deepseek_calls(monkeypatch, [_Resp(401)])
    assert deepseek.classify_intent({"deepseek-api-key": "k"}, "q", "x") == ERROR
    assert len(calls) == 1
    assert deepseek.classify_intent({}, "q", "x") == ERROR


# --- opening the thread: by link, never the wrong person's -------------------

class FakeThreadScreen:
    """`threads` = how many DM threads are stacked on screen; back() pops one."""

    def __init__(self, threads=0, stuck=False):
        self.threads, self.stuck, self.backs = threads, stuck, 0

    def find(self, **kw):
        return SimpleNamespace(exists=lambda *a, **k: self.threads > 0)

    def back(self):
        self.backs += 1
        if not self.stuck:
            self.threads = max(0, self.threads - 1)


def _open_thread(monkeypatch, plugin, screen, link_opens=True):
    plugin.ResourceID = m.resources("com.instagram.android")
    opened = []

    def fake_open(username):
        opened.append(username)
        if link_opens:
            screen.threads += 1
        return True

    monkeypatch.setattr(m, "open_instagram_dm", fake_open)
    monkeypatch.setattr(plugin, "_read_last_reply", lambda device: None)
    store = _store()
    plugin._process_user(screen, store, _queued(store)["ana"], None)
    return opened, store


def test_thread_opens_by_link_and_is_read(plugin, monkeypatch):
    opened, store = _open_thread(monkeypatch, plugin, FakeThreadScreen())
    assert opened == ["ana"]
    assert "unreachable" not in _queued(store)["ana"]


def test_thread_that_does_not_open_counts_as_a_miss(plugin, monkeypatch):
    _, store = _open_thread(monkeypatch, plugin, FakeThreadScreen(), link_opens=False)
    assert _queued(store)["ana"]["unreachable"] == 1


def test_previous_thread_is_left_before_opening_the_next(plugin, monkeypatch):
    screen = FakeThreadScreen(threads=1)
    opened, _ = _open_thread(monkeypatch, plugin, screen)
    assert opened == ["ana"] and screen.backs >= 1


def test_stuck_on_a_previous_thread_never_reads_it(plugin, monkeypatch):
    screen = FakeThreadScreen(threads=1, stuck=True)
    opened, store = _open_thread(monkeypatch, plugin, screen)
    assert opened == []  # nothing opened, nothing read or sent
    assert "unreachable" not in _queued(store)["ana"]
