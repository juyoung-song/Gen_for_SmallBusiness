"""브랜드 레퍼런스(이미지, 링크) 분석 서비스."""

import base64
import logging
from typing import Optional
from openai import OpenAI
from config.settings import Settings

logger = logging.getLogger(__name__)


class AnalysisService:
    """브랜드 온보딩 시 레퍼런스를 분석하여 고정 스타일 프롬프트를 추출하는 서비스."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: Optional[OpenAI] = None

    @property
    def client(self) -> OpenAI:
        """OpenAI 클라이언트 (lazy 초기화)."""
        if self._client is None:
            self._client = OpenAI(api_key=self.settings.OPENAI_API_KEY)
        return self._client

    async def analyze_brand_style(
        self, 
        brand_name: str,
        atmosphere: str,
        brand_color: str,
        reference_image_bytes: Optional[bytes] = None,
        reference_link: Optional[str] = None
    ) -> str:
        """레퍼런스 이미지나 링크를 분석하여 고정 스타일 프롬프트 생성.
        
        Args:
            brand_name: 브랜드명
            atmosphere: 브랜드 분위기 (사용자 입력)
            brand_color: 브랜드 색상 (사용자 입력)
            reference_image_bytes: 분석할 인스타 캡처 등 이미지 바이너리
            reference_link: 분석할 인스타 링크 (현재는 텍스트로만 참고)

        Returns:
            고정 스타일 프롬프트 문자열
        """
        logger.info("브랜드 스타일 분석 시작 (brand=%s)", brand_name)

        system_prompt = (
            "You are a professional brand identity consultant and prompt engineer for AI image generators. "
            "Your task is to analyze the user's brand information and reference images to create a 'Global Style Prompt'. "
            "This prompt will be used to maintain consistency across all generated marketing images for this brand."
        )

        user_content = [
            {
                "type": "text",
                "text": (
                    f"Brand Name: {brand_name}\n"
                    f"Requested Atmosphere: {atmosphere}\n"
                    f"Brand Color: {brand_color}\n"
                    f"Reference Link: {reference_link if reference_link else 'None'}\n\n"
                    "Based on the above and the attached reference image (if any), create a concise yet powerful "
                    "English style prompt (within 50-70 words). "
                    "Focus on photography style, lighting, composition, mood, and any recurring visual elements. "
                    "Output ONLY the English prompt text."
                )
            }
        ]

        if reference_image_bytes:
            # base64 인코딩
            base64_image = base64.b64encode(reference_image_bytes).decode("utf-8")
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                }
            })

        try:
            # Vision 지원 모델 사용 (settings.TEXT_MODEL이 gpt-4o 이상이라고 가정)
            response = self.client.chat.completions.create(
                model=self.settings.TEXT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                max_completion_tokens=300
            )

            style_prompt = response.choices[0].message.content.strip()
            logger.info("브랜드 스타일 분석 완료: %s", style_prompt[:100])
            return style_prompt

        except Exception as e:
            logger.error("브랜드 스타일 분석 중 오류 발생: %s", e)
            return f"High quality commercial photography, {atmosphere} mood, {brand_color} accents, centered composition, clean background."
