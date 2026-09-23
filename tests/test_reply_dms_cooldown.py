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
