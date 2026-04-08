"""staging 파일 저장 유틸 테스트.

design.md §4.4 '파일은 즉시 staging' 정책 지원:
- save_to_staging(bytes, extension=".jpg") → Path
- UUID 기반 유일한 파일명
- 실행 후 파일이 디스크에 존재하고 내용이 일치해야 한다
"""

from pathlib import Path

from utils.staging_storage import save_to_staging


class TestSaveToStaging:
    def test_writes_bytes_to_file_and_returns_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "utils.staging_storage.STAGING_DIR", tmp_path
        )
        raw = b"\x89PNG\r\n\x1a\nfake image bytes"
        path = save_to_staging(raw, extension=".png")

        assert isinstance(path, Path)
        assert path.exists()
        assert path.read_bytes() == raw
        assert path.suffix == ".png"
        assert path.parent == tmp_path

    def test_creates_unique_filenames_for_multiple_calls(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "utils.staging_storage.STAGING_DIR", tmp_path
        )
        a = save_to_staging(b"first", extension=".jpg")
        b = save_to_staging(b"second", extension=".jpg")
        assert a != b
        assert a.read_bytes() == b"first"
        assert b.read_bytes() == b"second"

    def test_creates_staging_dir_if_missing(self, tmp_path, monkeypatch):
        """STAGING_DIR 가 존재하지 않아도 자동 생성."""
        sub = tmp_path / "nested" / "staging"
        monkeypatch.setattr("utils.staging_storage.STAGING_DIR", sub)

        path = save_to_staging(b"data", extension=".jpg")
        assert sub.exists()
        assert path.parent == sub

    def test_default_extension_is_jpg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "utils.staging_storage.STAGING_DIR", tmp_path
        )
        path = save_to_staging(b"data")
        assert path.suffix == ".jpg"
