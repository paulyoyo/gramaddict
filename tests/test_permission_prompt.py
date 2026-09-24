"""Batch 15: an Android permission prompt in front of Instagram is answered
"Don't allow" instead of stopping the bot (2026-09-24 08:33 on the Pi)."""
import subprocess
from types import SimpleNamespace

import pytest

from GramAddict.core import bot_flow, utils
from GramAddict.core.device_facade import DeviceFacade
from GramAddict.core.resources import ResourceID

IG = "com.instagram.android"
PROMPT = "com.google.android.permissioncontroller"
DENY = "com.android.permissioncontroller:id/permission_deny_button"


class FakeSelector:
    def __init__(self, phone, kw):
        self.phone, self.kw = phone, kw

    def _matches(self):
        pattern = self.kw.get("resourceIdMatches", "")
        if self.phone.front != PROMPT:
            return None
        if "permission_message" in pattern:
            return "message"
        if "permission_deny" in pattern and self.phone.has_deny:
            return "deny"
        return None

    def exists(self, timeout=None):
        return self._matches() is not None

    def get_text(self):
        return "Allow Instagram to access photos and videos on this device?"

    def click(self):
        self.phone.clicks.append(self._matches())
        self.phone.front = IG  # denying returns to Instagram


class FakePhone:
    """deviceV2 stand-in: `front` is the package in the foreground."""

    def __init__(self, front, has_deny=True):
        self.front, self.has_deny, self.clicks, self.pressed = front, has_deny, [], []

    def __call__(self, **kw):
        return FakeSelector(self, kw)

    def app_current(self):
        return {"package": self.front}

    def press(self, key):
        self.pressed.append(key)
        self.front = IG

    def app_start(self, *a, **k):
        return None

    def set_fastinput_ime(self, on):
        pass


@pytest.fixture(autouse=True)
def _utils_env(monkeypatch):
    monkeypatch.setattr(utils, "sleep", lambda s: None)
    monkeypatch.setattr(utils, "random_sleep", lambda *a, **k: None)
    monkeypatch.setattr(utils, "app_id", IG, raising=False)
    monkeypatch.setattr(utils, "ResourceID", ResourceID(IG), raising=False)
    monkeypatch.setattr(
        utils,
        "configs",
        SimpleNamespace(
            device_id=None,
            args=SimpleNamespace(close_apps=False, screen_record=False, use_cloned_app=False),
        ),
        raising=False,
    )


def _device(phone):
    return SimpleNamespace(
        deviceV2=phone,
        find=lambda **kw: SimpleNamespace(exists=lambda *a: False, click=lambda: None),
    )


def test_denies_a_permission_prompt():
    phone = FakePhone(PROMPT)
    assert utils.dismiss_permission_prompt(_device(phone)) is True
    assert phone.clicks == ["deny"] and phone.front == IG


def test_no_prompt_nothing_to_do():
    phone = FakePhone(IG)
    assert utils.dismiss_permission_prompt(_device(phone)) is False
    assert phone.clicks == [] and phone.pressed == []


def test_prompt_without_a_deny_button_is_backed_out_of():
    phone = FakePhone(PROMPT, has_deny=False)
    assert utils.dismiss_permission_prompt(_device(phone)) is True
    assert phone.pressed == ["back"]


def test_open_instagram_gets_past_the_prompt(monkeypatch):
    monkeypatch.setattr(utils, "wait_for_instagram_ui", lambda device: True)
    monkeypatch.setattr(
        utils,
        "adb",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, "com.github.uiautomator/.FastInputIME", ""),
    )
    phone = FakePhone(PROMPT)
    # used to log "Unable to open Instagram. Bot will stop." and return False
    assert utils.open_instagram(_device(phone)) is True
    assert phone.clicks == ["deny"]


# --- between jobs: a closed Instagram ends the session instead of the process ----

class _Profile:
    def __init__(self, crash):
        self.crash = crash

    def getUsername(self):
        if self.crash:
            raise DeviceFacade.AppHasCrashed("App has crashed / has been closed!")
        return "me"


@pytest.mark.parametrize(
    "crash, reopens, expected, navigated",
    [
        (False, None, True, 0),  # already on your profile
        (True, True, True, 1),  # reopened: continue with the next job
        (True, False, False, 0),  # can't reopen: end the session, keep the bot alive
    ],
)
def test_back_to_own_profile(monkeypatch, crash, reopens, expected, navigated):
    monkeypatch.setattr(bot_flow, "open_instagram", lambda device: reopens)
    nav = []
    tab_bar = SimpleNamespace(navigateToProfile=lambda: nav.append(1))
    assert bot_flow.back_to_own_profile("dev", _Profile(crash), tab_bar, "me") is expected
    assert len(nav) == navigated
