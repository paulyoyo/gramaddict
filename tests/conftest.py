import pytest
import requests

import GramAddict.core.device_facade as device_facade
import GramAddict.core.filter as filter_module
import GramAddict.core.interaction as interaction
import GramAddict.core.utils as utils
import GramAddict.core.views as views

# Modules whose load_config() sets globals that tests overwrite directly.
_MODULE_GLOBALS = [
    (utils, ("args", "configs", "ResourceID", "app_id")),
    (filter_module, ("args", "configs", "ResourceID")),
    (interaction, ("args", "configs", "ResourceID")),
    (views, ("args", "configs", "ResourceID")),
    (device_facade, ("configs",)),
]


@pytest.fixture(autouse=True)
def _restore_module_globals(monkeypatch):
    """Whatever a test assigns to these globals is undone afterwards."""
    for module, names in _MODULE_GLOBALS:
        for name in names:
            monkeypatch.setattr(module, name, getattr(module, name, None), raising=False)


@pytest.fixture(autouse=True)
def _no_real_http(monkeypatch):
    """No test may reach DeepSeek, Slack, Telegram or PyPI. Tests fake
    requests.post/get themselves; anything that gets past them fails loudly."""

    def blocked(self, method, url, *a, **k):
        raise RuntimeError(f"real HTTP call in a test: {method} {url.split('?')[0][:40]}")

    monkeypatch.setattr(requests.sessions.Session, "request", blocked)
