"""인스타그램 연동 서비스 (API / Mock).
향후 실제 Meta API 및 ImgBB API로 교체될 수 있도록 구조화.
"""
import time
import logging
import requests
import base64

logger = logging.getLogger(__name__)

class InstagramService:
    def __init__(self, settings=None):
        self.settings = settings

    def upload_story(self, image_bytes: bytes, caption_text: str = ""):
        """
        [REAL] 스토리는 캡션이 필요 없지만(오버레이 텍스트 권장), 
        API 명세에 따라 share_to_story 플래그를 사용하여 업로드합니다.
        """
        if self.settings and not self.settings.USE_MOCK:
            # 실배포 로직 (피드와 유사하나 share_to_story=True)
            return self._upload_impl(image_bytes, caption_text, is_story=True)
        else:
            return self.upload_mock(image_bytes, caption_text, is_story=True)

    def upload_mock(self, image_bytes: bytes, caption_text: str, is_story: bool = False):
        """
        [MOCK] 스토리 여부에 따른 상태 메시지 분기를 추가합니다.
        """
        target = "스토리" if is_story else "피드"
        logger.info(f"Mock 인스타그램 {target} 업로드 시작")
        
        yield f"📡 이미지 호스팅 서버(ImgBB) 핑 테스트 중..."
        time.sleep(1.0)
        
        yield f"🖼️ {target} 미디어 업로드 중 (바이너리 -> URL 변환)..."
        time.sleep(1.5)
        
        yield f"📝 Instagram {target} 미디어 컨테이너 생성 중..."
        time.sleep(1.5)
        
        yield f"🚀 {target} 최종 배포(Publish) 중..."
        time.sleep(1.0)
        
        logger.info(f"Mock 인스타그램 {target} 업로드 완료")
        yield "DONE"

    def upload_real(self, image_bytes: bytes, caption_text: str):
         return self._upload_impl(image_bytes, caption_text, is_story=False)

    def _upload_impl(self, image_bytes: bytes, caption_text: str, is_story: bool = False):
        """실제 업로드 공통 구현체."""
        if not self.settings or not self.settings.is_instagram_ready:
            raise ValueError("실제 배포를 위해서는 인스타그램 설정이 필요합니다.")

        try:
            target_str = "스토리" if is_story else "피드"
            yield f"📡 {target_str}용 사진 포맷 최적화 및 서버 전송 중..."
            
            import io
            from PIL import Image
            img = Image.open(io.BytesIO(image_bytes))
            if img.mode != "RGB":
                img = img.convert("RGB")
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG")
            jpeg_bytes = buffer.getvalue()

            freeimage_url = "https://freeimage.host/api/1/upload"
            payload = {
                "key": self.settings.FREEIMAGE_API_KEY,
                "action": "upload",
                "source": base64.b64encode(jpeg_bytes).decode('utf-8'),
                "format": "json"
            }
            res_img = requests.post(freeimage_url, data=payload)
            res_img.raise_for_status()
            
            public_image_url = res_img.json().get("image", {}).get("url")
            if not public_image_url:
                raise ValueError("URL 발급 실패")
            
            yield f"🔗 Meta Graph API와 연결하여 {target_str}를 준비합니다..."
            ig_id = self.settings.INSTAGRAM_ACCOUNT_ID
            access_token = self.settings.META_ACCESS_TOKEN
            
            media_url = f"https://graph.facebook.com/v19.0/{ig_id}/media"
            media_payload = {
                "image_url": public_image_url,
                "access_token": access_token
            }
            if is_story:
                # 스토리 업로드용 파라미터 (명세에 따라 다를 수 있음)
                media_payload["media_type"] = "STORIES"
            else:
                media_payload["caption"] = caption_text

            res_media = requests.post(media_url, data=media_payload)
            res_media.raise_for_status()
            creation_id = res_media.json().get("id")
            
            yield f"🚀 {target_str} 게시를 완료합니다!"
            publish_url = f"https://graph.facebook.com/v19.0/{ig_id}/media_publish"
            publish_payload = {
                "creation_id": creation_id,
                "access_token": access_token
            }
            res_pub = requests.post(publish_url, data=publish_payload)
            res_pub.raise_for_status()
            yield "DONE"

        except Exception as e:
            logger.exception("업로드 실패")
            raise RuntimeError(f"{target_str} 업로드 실패: {str(e)}")
