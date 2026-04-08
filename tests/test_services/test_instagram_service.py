"""InstagramService 테스트 — Step 2.4 post id 기록.

업로드 제너레이터가 소진되면 last_post_id 와 last_posted_at 이 채워진다.
Mock 모드는 외부 호출 없이 빠르게 검증 가능 (sleep 은 stub 으로 우회).
"""

from datetime import datetime

import pytest

from services.instagram_service import InstagramService


class _FakeSettings:
    USE_MOCK = True


class TestInstagramMockUploadRecordsPostId:
    def test_last_post_id_is_none_before_upload(self):
        service = InstagramService(_FakeSettings())
        assert service.last_post_id is None
        assert service.last_posted_at is None

    def test_mock_upload_sets_last_post_id_and_timestamp(self, monkeypatch):
        """Mock 업로드 제너레이터를 소진하면 post id + 시각이 채워진다."""
        # sleep 우회 (테스트 빠르게)
        monkeypatch.setattr("services.instagram_service.time.sleep", lambda *_: None)

        service = InstagramService(_FakeSettings())

        # 제너레이터 소진
        messages = list(service.upload_mock(b"fake img", "caption", is_story=False))

        assert messages[-1] == "DONE"
        assert service.last_post_id is not None
        assert service.last_post_id.startswith("mock_")
        assert isinstance(service.last_posted_at, datetime)

    def test_mock_story_upload_also_records_post_id(self, monkeypatch):
        monkeypatch.setattr("services.instagram_service.time.sleep", lambda *_: None)

        service = InstagramService(_FakeSettings())
        list(service.upload_mock(b"fake", "", is_story=True))

        assert service.last_post_id is not None
        assert service.last_post_id.startswith("mock_")

    def test_consecutive_uploads_overwrite_last_post_id(self, monkeypatch):
        """매번 새 업로드가 last_post_id 를 덮어쓴다."""
        monkeypatch.setattr("services.instagram_service.time.sleep", lambda *_: None)

        service = InstagramService(_FakeSettings())
        list(service.upload_mock(b"a", "1"))
        first = service.last_post_id
        list(service.upload_mock(b"b", "2"))
        second = service.last_post_id

        assert first is not None
        assert second is not None
        assert first != second
