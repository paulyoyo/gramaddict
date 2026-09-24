import os
from pathlib import Path

from GramAddict.core.interaction import _load_and_clean_txt_file

HERE = Path(__file__).parent


def _use_file(monkeypatch, name):
    path = str(HERE / "txt" / name)
    monkeypatch.setattr(os.path, "join", lambda *a: path)


def test_load_txt_ok(monkeypatch):
    _use_file(monkeypatch, "txt_ok.txt")
    message = _load_and_clean_txt_file("test_user", "txt_filename")
    assert message is not None
    assert message == [
        "Hello, test_user! How are you today?",
        "Hello everyone!",
        "Goodbye, test_user! Have a great day!",
    ]


def test_load_txt_empty(monkeypatch):
    _use_file(monkeypatch, "txt_empty.txt")
    message = _load_and_clean_txt_file("test_user", "txt_filename")
    assert message is None


def test_load_txt_not_exists(monkeypatch):
    _use_file(monkeypatch, "txt_not_exists.txt")
    message = _load_and_clean_txt_file("test_user", "txt_filename")
    assert message is None
