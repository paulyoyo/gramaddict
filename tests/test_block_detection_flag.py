"""disable-block-detection must mean what it says, parsed by the bot's real Config.

2026-09-23: the flag was store_false, so `disable-block-detection: false` gave True
and detect_block() returned early: block detection was off on the Pi."""
import sys

import pytest

from GramAddict.core.config import Config


def _parse(tmp_path, monkeypatch, line):
    config = tmp_path / "config.yml"
    config.write_text("username: tester\n" + (line + "\n" if line else ""))
    monkeypatch.setattr(sys, "argv", ["run.py", "--config", str(config)])
    return Config(first_run=False).args.disable_block_detection


@pytest.mark.parametrize(
    "line, disabled",
    [
        ("disable-block-detection: false", False),
        ("disable-block-detection: true", True),
        (None, False),  # not set: detection stays on
    ],
)
def test_disable_block_detection_setting(tmp_path, monkeypatch, line, disabled):
    assert _parse(tmp_path, monkeypatch, line) is disabled
