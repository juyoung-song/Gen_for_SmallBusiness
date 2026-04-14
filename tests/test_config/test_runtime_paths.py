from pathlib import Path

from config.runtime_paths import get_app_data_dir, get_sqlite_db_path


def test_get_app_data_dir_uses_env(tmp_path, monkeypatch):
    custom = tmp_path / "brewgram-data"
    monkeypatch.setenv("APP_DATA_DIR", str(custom))

    result = get_app_data_dir()

    assert result == custom.resolve()
    assert result.is_dir()


def test_get_sqlite_db_path_defaults_under_app_data_dir(tmp_path, monkeypatch):
    custom = tmp_path / "brewgram-data"
    monkeypatch.setenv("APP_DATA_DIR", str(custom))
    monkeypatch.delenv("SQLITE_DB_PATH", raising=False)

    result = get_sqlite_db_path()

    assert result == (custom / "history.db").resolve()
    assert result.parent.is_dir()


def test_get_sqlite_db_path_prefers_explicit_env(tmp_path, monkeypatch):
    custom = tmp_path / "external" / "prod.db"
    monkeypatch.setenv("SQLITE_DB_PATH", str(custom))

    result = get_sqlite_db_path()

    assert result == custom.resolve()
    assert result.parent.is_dir()
