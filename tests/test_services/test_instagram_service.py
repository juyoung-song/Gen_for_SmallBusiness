"""InstagramService 테스트 — Step 2.4 post id 기록 + song fd465f8 폴링.

업로드 제너레이터가 소진되면 last_post_id 와 last_posted_at 이 채워진다.
Mock 모드는 외부 호출 없이 빠르게 검증 가능 (sleep 은 stub 으로 우회).

song fd465f8 이식 검증:
    real 업로드 경로에서 /media 응답 이후 publish 전에
    /{creation_id}?fields=status_code 를 폴링해 FINISHED 가 된 후에만
    publish 를 호출해야 한다. 첫 호출부터 publish 하면 Meta 가 code=9007
    "Media ID is not available" 로 거부한다.
"""

from datetime import datetime

import pytest

from services.instagram_service import InstagramService


class _FakeSettings:
    """instagram_service 가 사용하는 최소 인터페이스만 stub."""

    is_mock_image = True
    FREEIMAGE_API_KEY = "test"
    META_ACCESS_TOKEN = "test"
    INSTAGRAM_ACCOUNT_ID = "test"

    @property
    def is_instagram_ready(self) -> bool:
        return True


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


# ══════════════════════════════════════════════════════════════════════
# song fd465f8: /media → status_code 폴링 → publish
# ══════════════════════════════════════════════════════════════════════


class _RealSettings:
    """_upload_impl (real 경로) 진입용 stub. is_mock_image=False."""

    is_mock_image = False
    FREEIMAGE_API_KEY = "test-key"
    META_ACCESS_TOKEN = "test-token"
    INSTAGRAM_ACCOUNT_ID = "1784000000000000"

    @property
    def is_instagram_ready(self) -> bool:
        return True


class _FakeResponse:
    """최소 httpx.Response 스텁."""

    def __init__(self, *, status_code: int = 200, json_data=None, text: str = ""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}: {self.text}")


def _make_jpeg_bytes() -> bytes:
    """테스트용 최소 JPEG 바이트 (Pillow 가 열 수 있을 정도)."""
    import io as _io

    from PIL import Image

    img = Image.new("RGB", (10, 10), color="white")
    buf = _io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class TestUploadPollsStatusBeforePublish:
    """fd465f8: create→publish 사이에 status_code 폴링이 있는지 검증."""

    def test_happy_path_polls_until_finished_then_publishes(self, monkeypatch):
        """첫 status 조회 IN_PROGRESS → 두 번째 FINISHED → publish 성공."""
        # sleep 우회 (poll_interval 1.5s * N 을 무시)
        monkeypatch.setattr("services.instagram_service.time.sleep", lambda *_: None)

        # POST 호출 카운터로 단계 식별
        post_calls = []

        def fake_post(url, data=None, timeout=None, **_):
            post_calls.append(url)
            if "freeimage.host" in url:
                return _FakeResponse(
                    json_data={"image": {"url": "https://cdn.example/test.jpg"}}
                )
            if "/media_publish" in url:
                return _FakeResponse(json_data={"id": "99999"})
            if url.endswith("/media"):
                return _FakeResponse(json_data={"id": "CREATION_ID_42"})
            raise AssertionError(f"unexpected POST url: {url}")

        # GET 호출 순서대로 status_code 전이
        get_statuses = ["IN_PROGRESS", "FINISHED"]
        get_calls = []

        def fake_get(url, params=None, timeout=None, **_):
            get_calls.append((url, params))
            if "/CREATION_ID_42" not in url:
                raise AssertionError(f"unexpected GET url: {url}")
            if not get_statuses:
                raise AssertionError("too many status polls")
            next_status = get_statuses.pop(0)
            return _FakeResponse(json_data={"status_code": next_status})

        monkeypatch.setattr("services.instagram_service.httpx.post", fake_post)
        monkeypatch.setattr("services.instagram_service.httpx.get", fake_get)

        service = InstagramService(_RealSettings())
        messages = list(service.upload_real(_make_jpeg_bytes(), "caption"))

        # 핵심: status_code 폴링이 일어났고 FINISHED 후에만 publish 됨
        assert len(get_calls) == 2, (
            f"폴링이 2번 일어나야 함 (IN_PROGRESS→FINISHED), 실제={len(get_calls)}"
        )
        assert any("/media_publish" in u for u in post_calls), (
            "publish 가 호출되지 않음 — 폴링 후에도 publish 까지 도달해야 함"
        )

        # publish 순서가 마지막 POST 여야 함 (create → publish)
        publish_idx = next(
            i for i, u in enumerate(post_calls) if "/media_publish" in u
        )
        media_idx = next(i for i, u in enumerate(post_calls) if u.endswith("/media"))
        assert publish_idx > media_idx, (
            "순서 위반: /media 다음에 /media_publish 가 호출돼야 함"
        )

        # 결과 확인
        assert messages[-1] == "DONE"
        assert service.last_post_id == "99999"
        assert isinstance(service.last_posted_at, datetime)

    def test_status_error_aborts_without_publish(self, monkeypatch):
        """status 가 ERROR 면 publish 없이 즉시 중단.

        폴링이 있어야만 의미 있는 테스트 → get_calls >= 1 을 강제로 assert
        하여 false-positive GREEN (폴링 없이도 publish assertion 이 발동하는 경로)
        을 막는다.
        """
        monkeypatch.setattr("services.instagram_service.time.sleep", lambda *_: None)

        get_calls: list = []
        publish_called: list = []

        def fake_post(url, data=None, timeout=None, **_):
            if "freeimage.host" in url:
                return _FakeResponse(
                    json_data={"image": {"url": "https://cdn.example/x.jpg"}}
                )
            if "/media_publish" in url:
                publish_called.append(url)
                # 폴링 없이 바로 이 경로로 오면 명시적으로 실패 — 에러 메시지 차별화
                return _FakeResponse(
                    status_code=500, text="publish should not be called on ERROR"
                )
            if url.endswith("/media"):
                return _FakeResponse(json_data={"id": "BAD_CID"})
            raise AssertionError(url)

        def fake_get(url, params=None, timeout=None, **_):
            get_calls.append(url)
            return _FakeResponse(json_data={"status_code": "ERROR"})

        monkeypatch.setattr("services.instagram_service.httpx.post", fake_post)
        monkeypatch.setattr("services.instagram_service.httpx.get", fake_get)

        service = InstagramService(_RealSettings())
        with pytest.raises(RuntimeError, match="피드 업로드 실패"):
            list(service.upload_real(_make_jpeg_bytes(), "caption"))

        assert len(get_calls) >= 1, (
            "status 폴링 GET 이 최소 1번은 일어나야 함 (ERROR 감지 경로)"
        )
        assert publish_called == [], (
            f"ERROR status 에서 publish 가 호출됨 — 폴링 미구현 증거. called={publish_called}"
        )

    def test_timeout_when_never_finished(self, monkeypatch):
        """status 가 계속 IN_PROGRESS 면 max_wait 초과 후 타임아웃.

        폴링 없이는 타임아웃 자체가 존재할 수 없으므로 get_calls >= 2 를
        강제해 false-positive GREEN 을 차단.
        """
        monkeypatch.setattr("services.instagram_service.time.sleep", lambda *_: None)

        get_calls: list = []
        publish_called: list = []

        def fake_post(url, data=None, timeout=None, **_):
            if "freeimage.host" in url:
                return _FakeResponse(
                    json_data={"image": {"url": "https://cdn.example/y.jpg"}}
                )
            if "/media_publish" in url:
                publish_called.append(url)
                return _FakeResponse(
                    status_code=500, text="publish should not be called on timeout"
                )
            if url.endswith("/media"):
                return _FakeResponse(json_data={"id": "SLOW_CID"})
            raise AssertionError(url)

        def fake_get(url, params=None, timeout=None, **_):
            get_calls.append(url)
            return _FakeResponse(json_data={"status_code": "IN_PROGRESS"})

        monkeypatch.setattr("services.instagram_service.httpx.post", fake_post)
        monkeypatch.setattr("services.instagram_service.httpx.get", fake_get)

        service = InstagramService(_RealSettings())
        with pytest.raises(RuntimeError, match="피드 업로드 실패"):
            list(service.upload_real(_make_jpeg_bytes(), "caption"))

        assert len(get_calls) >= 2, (
            f"타임아웃까지 폴링이 여러 번 일어나야 함, 실제={len(get_calls)}"
        )
        assert publish_called == [], (
            f"타임아웃 상황에서 publish 호출됨 — 폴링 미구현. called={publish_called}"
        )
