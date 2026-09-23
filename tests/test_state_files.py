import json

import pytest

from GramAddict.core.persistent_list import PersistentList
from GramAddict.core.storage import Storage


class _Encoder:
    def default(self, o):
        return o


def _sessions_file(tmp_path):
    return tmp_path / "accounts" / "me" / "sessions.json"


def test_persist_merges_with_existing_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = _sessions_file(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps([{"id": "old"}]))

    sessions = PersistentList("sessions", _Encoder)
    sessions.append({"id": "new"})
    sessions.persist("me")

    assert [s["id"] for s in json.loads(path.read_text())] == ["old", "new"]


def test_failed_persist_keeps_existing_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = _sessions_file(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps([{"id": "old"}]))

    sessions = PersistentList("sessions", _Encoder)
    sessions.append({"no_id": True})
    with pytest.raises(Exception):
        sessions.persist("me")

    assert json.loads(path.read_text()) == [{"id": "old"}]


def test_corrupt_sessions_file_exits_non_zero(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = _sessions_file(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{not json")

    with pytest.raises(SystemExit) as exc:
        PersistentList("sessions", _Encoder).persist("me")
    assert exc.value.code == 1
    assert path.read_text() == "{not json"


def test_corrupt_interacted_users_exits_non_zero(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    account = tmp_path / "accounts" / "me"
    account.mkdir(parents=True)
    (account / "interacted_users.json").write_text("{not json")

    with pytest.raises(SystemExit) as exc:
        Storage("me")
    assert exc.value.code == 1


def test_storage_loads_state_and_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    account = tmp_path / "accounts" / "me"
    account.mkdir(parents=True)
    (account / "interacted_users.json").write_text(json.dumps({"bob": {}}))

    storage = Storage("me")
    assert storage.interacted_users == {"bob": {}}
    assert storage.history_filter_users == {}
    assert storage.pending_replies == []


def test_storage_without_username_raises():
    with pytest.raises(ValueError):
        Storage(None)
