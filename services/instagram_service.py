"""인스타그램 연동 서비스 (API / Mock).

검증된 로직(FreeImage + Meta Graph v19.0) 기반. 스토리 기능 확장 포함.

Step 1.3 수정:
- C-1: FreeImage API 키 하드코딩 → Settings.FREEIMAGE_API_KEY 로 분리
- C-3: `requests` → `httpx` 로 통일 (requests 는 본 프로젝트 의존성 아님)
- bare RuntimeError 의 target_str unbound 버그 수정

Step 2.4 추가:
- 게시 성공 시 Meta post id 를 self.last_post_id 에 저장 → 호출부가 DB 저장에 사용
- Mock 모드도 가짜 post id 를 만들어 동일한 패턴으로 동작
"""

import base64
import io
import logging
import time
import uuid
from datetime import datetime, timezone

import httpx
from PIL import Image

logger = logging.getLogger(__name__)


class InstagramService:
    def __init__(self, settings=None):
        self.settings = settings
        # Step 2.4: 게시 성공 후 호출부가 읽을 수 있도록 마지막 post 정보 저장
        self.last_post_id: str | None = None
        self.last_posted_at: datetime | None = None

    def upload_story(self, image_bytes: bytes, caption_text: str = ""):
        """스토리 업로드. IMAGE_BACKEND_KIND=mock 이면 시뮬레이션."""
        if self.settings and not self.settings.is_mock_image:
            return self._upload_impl(image_bytes, caption_text, is_story=True)
        return self.upload_mock(image_bytes, caption_text, is_story=True)

    def upload_real(self, image_bytes: bytes, caption_text: str):
        """피드 업로드. IMAGE_BACKEND_KIND=mock 이면 시뮬레이션."""
        if self.settings and not self.settings.is_mock_image:
            return self._upload_impl(image_bytes, caption_text, is_story=False)
        return self.upload_mock(image_bytes, caption_text, is_story=False)

    def upload_mock(
        self, image_bytes: bytes, caption_text: str, is_story: bool = False
    ):
        """[MOCK] 업로드 시뮬레이션."""
        target = "스토리" if is_story else "피드"
        yield f"📡 이미지 호스팅 서버({target}) 핑 테스트 중..."
        time.sleep(1.0)
        yield f"🖼️ {target} 미디어 URL 변환 중..."
        time.sleep(1.5)
        yield f"🚀 {target} 최종 배포 완료 시뮬레이션..."
        time.sleep(1.0)
        # Step 2.4: Mock 도 실제 흐름과 동일하게 post id/시각을 기록
        self.last_post_id = f"mock_{uuid.uuid4().hex[:12]}"
        self.last_posted_at = datetime.now(timezone.utc)
        yield "DONE"

    def _upload_impl(
        self, image_bytes: bytes, caption_text: str, is_story: bool = False
    ):
        """FreeImage 호스팅 + Meta Graph API 업로드."""
        target_str = "스토리" if is_story else "피드"

        if not self.settings or not self.settings.is_instagram_ready:
            raise ValueError("실제 배포를 위해서는 인스타그램 설정(.env)이 필요합니다.")

        try:
            yield f"📡 사진을 인스타 전용 포맷(JPEG)으로 최적화하여 서버에 올리는 중..."

            # 1. JPEG 변환
            img = Image.open(io.BytesIO(image_bytes))
            if img.mode != "RGB":
                img = img.convert("RGB")
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG")
            jpeg_bytes = buffer.getvalue()

            # 2. 이미지 호스팅 (C-1: API 키를 Settings 로 분리)
            freeimage_url = "https://freeimage.host/api/1/upload"
            payload = {
                "key": self.settings.FREEIMAGE_API_KEY,
                "action": "upload",
                "source": base64.b64encode(jpeg_bytes).decode("utf-8"),
                "format": "json",
            }
            res_img = httpx.post(freeimage_url, data=payload, timeout=30.0)
            res_img.raise_for_status()

            public_image_url = res_img.json().get("image", {}).get("url")
            if not public_image_url:
                raise ValueError(
                    "이미지 호스팅 서버(FreeImage)가 주소를 반환하지 않았습니다."
                )

            logger.info("Public URL 발급 성공: %s", public_image_url)

            # 3. Meta Graph API v19.0
            yield f"🔗 Meta 서버와 연결하여 {target_str}를 준비 중입니다..."
            ig_id = self.settings.INSTAGRAM_ACCOUNT_ID
            access_token = self.settings.META_ACCESS_TOKEN

            media_url = f"https://graph.facebook.com/v19.0/{ig_id}/media"

            # 스토리와 피드의 파라미터를 완전히 분리
            media_payload = {
                "image_url": public_image_url,
                "access_token": access_token,
            }
            if is_story:
                # 스토리는 오직 이 필드만 (caption 절대 금지)
                media_payload["media_type"] = "STORIES"
            else:
                # 피드는 캡션 + 타입 명시
                media_payload["caption"] = caption_text
                media_payload["media_type"] = "IMAGE"

            res_media = httpx.post(media_url, data=media_payload, timeout=60.0)
            if res_media.status_code != 200:
                err_text = res_media.text
                logger.error("Meta 미디어 생성 실패: %s", err_text)
                raise ValueError(f"Meta 서버 거부: {err_text}")

            creation_id = res_media.json().get("id")

            # 4. 미디어 처리 상태 폴링 (song fd465f8 이식)
            # Meta 는 /media 호출 직후 creation_id 를 즉시 반환하지만, 실제로는
            # 백그라운드에서 image_url 다운로드/검증/리사이즈를 수행한다.
            # 곧바로 publish 를 호출하면 code=9007 "Media ID is not available"
            # 에러가 발생하고, 같은 요청을 두 번 눌러야 성공하는 증상이 생긴다.
            # /{creation_id}?fields=status_code 를 폴링해 FINISHED 가 된 후에만
            # publish 를 호출한다. song 원본 fd465f8 의 파라미터를 그대로 사용:
            #   max_wait_seconds=30, poll_interval=1.5
            # (won 은 httpx 기반이라 requests.get → httpx.get 으로만 어댑트)
            yield f"⏳ {target_str} 미디어를 Meta 서버가 처리할 때까지 잠시 기다리는 중..."
            status_url = f"https://graph.facebook.com/v19.0/{creation_id}"
            max_wait_seconds = 30
            poll_interval = 1.5
            waited = 0.0
            final_status: str | None = None
            while waited < max_wait_seconds:
                status_resp = httpx.get(
                    status_url,
                    params={
                        "fields": "status_code",
                        "access_token": access_token,
                    },
                    timeout=30.0,
                )
                if status_resp.status_code != 200:
                    logger.error("미디어 상태 조회 실패: %s", status_resp.text)
                    raise ValueError(
                        f"미디어 상태 조회 실패: {status_resp.text}"
                    )
                final_status = status_resp.json().get("status_code")
                logger.info(
                    "미디어 상태 조회: %s (경과 %.1fs)", final_status, waited
                )
                if final_status == "FINISHED":
                    break
                if final_status in ("ERROR", "EXPIRED"):
                    raise ValueError(
                        f"Meta 미디어 처리 실패 (status={final_status})"
                    )
                time.sleep(poll_interval)
                waited += poll_interval

            if final_status != "FINISHED":
                raise ValueError(
                    f"{target_str} 미디어 준비 시간 초과 "
                    f"({max_wait_seconds}s). 잠시 후 다시 시도해주세요."
                )

            # 5. 최종 게시
            yield f"🚀 거의 다 되었습니다! {target_str}를 최종 발행합니다!"
            publish_url = f"https://graph.facebook.com/v19.0/{ig_id}/media_publish"
            publish_payload = {
                "creation_id": creation_id,
                "access_token": access_token,
            }
            res_pub = httpx.post(publish_url, data=publish_payload, timeout=60.0)
            if res_pub.status_code != 200:
                err_text_pub = res_pub.text
                logger.error("Meta 게시 실패: %s", err_text_pub)
                raise ValueError(f"최종 게시 거부: {err_text_pub}")

            # Step 2.4: Meta 가 반환한 media id 를 저장
            published_id = res_pub.json().get("id")
            self.last_post_id = str(published_id) if published_id else None
            self.last_posted_at = datetime.now(timezone.utc)

            yield "DONE"

        except Exception as e:
            logger.exception("인스타그램 업로드 치명적 오류")
            raise RuntimeError(f"{target_str} 업로드 실패: {e}")
