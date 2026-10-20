from pathlib import Path

from lcarsai.config import default_data_dir, ensure_private_directory


def test_data_dir_override_is_respected(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "chosen" / "data"
    monkeypatch.setenv("LCARSAI_DATA_DIR", str(target))
    assert default_data_dir() == target


def test_ensure_private_directory_creates_directory(tmp_path: Path) -> None:
    target = tmp_path / "new" / "folder"
    assert ensure_private_directory(target) == target
    assert target.is_dir()
