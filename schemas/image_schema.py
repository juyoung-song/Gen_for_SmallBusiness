"""이미지 생성 입출력 스키마.

architecture.md 7.2 기준:
- ImageGenerationRequest: 사용자 입력 (프롬프트, 스타일)
- ImageGenerationResponse: 생성 결과 (이미지 바이너리, 프롬프트)
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from schemas.text_schema import VALID_STYLES


class ImageGenerationRequest(BaseModel):
    """광고 이미지 생성 요청."""

    prompt: str = Field(
        default="",
        description="참조용 광고 문구",
    )
    product_name: str = Field(
        default="",
        description="상품명",
    )
    description: str = Field(
        default="",
        description="상품 설명",
    )
    goal: str = Field(
        default="일반 홍보",
        description="홍보 목적",
    )
    style: str = Field(
        default="기본",
        description="이미지 스타일 (기본/감성/고급/유머/심플)",
    )
    image_data: bytes | None = Field(
        default=None,
        description="참조용 업로드 이미지",
    )

    @field_validator("style")
    @classmethod
    def validate_style(cls, v: str) -> str:
        """허용된 스타일인지 검증."""
        return v if v in VALID_STYLES else "기본"


class ImageGenerationResponse(BaseModel):
    """광고 이미지 생성 응답.

    image_data: Mock에서는 Pillow 생성 PNG, API에서는 다운로드된 이미지 bytes.
    st.image()에 바로 전달 가능.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    image_data: bytes = Field(
        default=b"",
        description="이미지 바이너리 데이터 (PNG)",
    )
    revised_prompt: str = Field(
        default="",
        description="실제 사용된 프롬프트 (DALL-E 수정 포함)",
    )
