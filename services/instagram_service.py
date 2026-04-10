"""인스타그램 연동 서비스 (API / Mock).
백업본의 검증된 로직(FreeImage + v19.0) 기반으로 복구 및 스토리 기능 추가.
"""
import time
import logging
import requests
import base64
import io
from PIL import Image

logger = logging.getLogger(__name__)

class InstagramService:
    def __init__(self, settings=None):
        self.settings = settings

    def upload_story(self, image_bytes: bytes, caption_text: str = ""):
        """[REAL] 검증된 로직 기반 스토리 업로드"""
        if self.settings and not self.settings.USE_MOCK:
            return self._upload_impl(image_bytes, caption_text, is_story=True)
        else:
            return self.upload_mock(image_bytes, caption_text, is_story=True)

    def upload_real(self, image_bytes: bytes, caption_text: str):
        """[REAL] 검증된 로직 기반 피드 업로드"""
        if self.settings and not self.settings.USE_MOCK:
            return self._upload_impl(image_bytes, caption_text, is_story=False)
        else:
            return self.upload_mock(image_bytes, caption_text, is_story=False)

    def upload_mock(self, image_bytes: bytes, caption_text: str, is_story: bool = False):
        """[MOCK] 업로드 시뮬레이션"""
        target = "스토리" if is_story else "피드"
        yield f"📡 이미지 호스팅 서버({target}) 핑 테스트 중..."
        time.sleep(1.0)
        yield f"🖼️ {target} 미디어 URL 변환 중..."
        time.sleep(1.5)
        yield f"🚀 {target} 최종 배포 완료 시뮬레이션..."
        time.sleep(1.0)
        yield "DONE"

    def _upload_impl(self, image_bytes: bytes, caption_text: str, is_story: bool = False):
        """백업본의 정답 로직을 그대로 구현하되 스토리 기능만 확장"""
        if not self.settings or not self.settings.is_instagram_ready:
            raise ValueError("실제 배포를 위해서는 인스타그램 설정(.env)이 필요합니다.")

        try:
            target_str = "스토리" if is_story else "피드"
            yield f"📡 사진을 인스타 전용 포맷(JPEG)으로 최적화하여 서버에 올리는 중..."
            
            # 1. JPEG 변환
            img = Image.open(io.BytesIO(image_bytes))
            if img.mode != "RGB":
                img = img.convert("RGB")
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG")
            jpeg_bytes = buffer.getvalue()

            # 2. 이미지 호스팅 (백업본에서 검증된 FreeImage.host 공용 키 사용)
            freeimage_url = "https://freeimage.host/api/1/upload"
            payload = {
                "key": "6d207e02198a847aa98d0a2a901485a5", # 백업본의 정답 키
                "action": "upload",
                "source": base64.b64encode(jpeg_bytes).decode('utf-8'),
                "format": "json"
            }
            res_img = requests.post(freeimage_url, data=payload)
            res_img.raise_for_status()
            
            public_image_url = res_img.json().get("image", {}).get("url")
            if not public_image_url:
                raise ValueError("이미지 호스팅 서버(FreeImage)가 주소를 반환하지 않았습니다.")
            
            logger.info(f"Public URL 발급 성공: {public_image_url}")

            # 3. Meta Graph API (v19.0 - 백업본과 동일 설정)
            yield f"🔗 Meta 서버와 연결하여 {target_str}를 준비 중입니다..."
            ig_id = self.settings.INSTAGRAM_ACCOUNT_ID
            access_token = self.settings.META_ACCESS_TOKEN
            
            media_url = f"https://graph.facebook.com/v19.0/{ig_id}/media"
            
            # 스토리와 피드의 파라미터를 완전히 분리하여 전송
            media_payload = {
                "image_url": public_image_url,
                "access_token": access_token
            }
            
            if is_story:
                # 스토리는 오직 이 필드만 있어야 합니다 (caption 절대 금지)
                media_payload["media_type"] = "STORIES"
            else:
                # 피드는 캡션이 필수/권장입니다
                media_payload["caption"] = caption_text
                media_payload["media_type"] = "IMAGE" # 명시적으로 지정
            
            # data= 방식을 유지 (백업본 성공 방식)
            res_media = requests.post(media_url, data=media_payload)
            
            if res_media.status_code != 200:
                err_text = res_media.text
                logger.error(f"Meta 미디어 생성 실패: {err_text}")
                raise ValueError(f"Meta 서버 거부: {err_text}")
                
            creation_id = res_media.json().get("id")

            # 4. 미디어 처리 상태 폴링 (FINISHED 될 때까지 대기)
            # Meta 가 image_url 을 비동기로 내려받아 처리하므로, 곧바로
            # publish 를 호출하면 code=9007 "Media ID is not available" 발생.
            # /{creation_id}?fields=status_code 로 상태를 폴링해야 함.
            yield f"⏳ {target_str} 미디어를 Meta 서버가 처리할 때까지 잠시 기다리는 중..."
            status_url = f"https://graph.facebook.com/v19.0/{creation_id}"
            max_wait_seconds = 30
            poll_interval = 1.5
            waited = 0.0
            final_status = None
            while waited < max_wait_seconds:
                status_resp = requests.get(
                    status_url,
                    params={"fields": "status_code", "access_token": access_token},
                )
                if status_resp.status_code != 200:
                    logger.error(f"미디어 상태 조회 실패: {status_resp.text}")
                    raise ValueError(f"미디어 상태 조회 실패: {status_resp.text}")
                final_status = status_resp.json().get("status_code")
                logger.info(f"미디어 상태 조회: {final_status} (경과 {waited:.1f}s)")
                if final_status == "FINISHED":
                    break
                if final_status in ("ERROR", "EXPIRED"):
                    raise ValueError(f"Meta 미디어 처리 실패 (status={final_status})")
                time.sleep(poll_interval)
                waited += poll_interval

            if final_status != "FINISHED":
                raise ValueError(
                    f"{target_str} 미디어 준비 시간 초과 ({max_wait_seconds}s). 잠시 후 다시 시도해주세요."
                )

            # 5. 최종 게시 (Publish)
            yield f"🚀 거의 다 되었습니다! {target_str}를 최종 발행합니다!"
            publish_url = f"https://graph.facebook.com/v19.0/{ig_id}/media_publish"
            publish_payload = {
                "creation_id": creation_id,
                "access_token": access_token
            }
            res_pub = requests.post(publish_url, data=publish_payload)
            
            if res_pub.status_code != 200:
                err_text_pub = res_pub.text
                logger.error(f"Meta 게시 실패: {err_text_pub}")
                raise ValueError(f"최종 게시 거부: {err_text_pub}")
                
            yield "DONE"

        except Exception as e:
            logger.exception("인스타그램 업로드 치명적 오류")
            raise RuntimeError(f"{target_str} 업로드 실패: {str(e)}")
