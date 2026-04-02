"""텍스트 생성 입출력 스키마.

architecture.md 7.1 기준:
- TextGenerationRequest: 사용자 입력 (상품명, 설명, 스타일)
- TextGenerationResponse: AI 생성 결과 (광고 문구 3개 + 홍보 문장 2개)
"""

from pydantic import BaseModel, Field, field_validator

# 허용 스타일 목록
VALID_STYLES: list[str] = ["기본", "감성", "고급", "유머", "심플"]


class TextGenerationRequest(BaseModel):
    """광고 문구 생성 요청."""

    product_name: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="상품명 (필수, 최대 50자)",
    )
    description: str = Field(
        default="",
        max_length=200,
        description="상품 설명 (선택, 최대 200자)",
    )
    style: str = Field(
        default="기본",
        description="광고 스타일 (기본/감성/고급/유머/심플)",
    )
    goal: str = Field(
        default="일반 홍보",
        description="홍보 목적 (신상품 홍보, 할인 행사, 매장 소개, 시즌 홍보 등)",
    )
    image_data: bytes | None = Field(
        default=None,
        description="업로드된 상품 이미지 바이너리",
    )

    @field_validator("product_name")
    @classmethod
    def strip_product_name(cls, v: str) -> str:
        """앞뒤 공백 제거."""
        return v.strip()

    @field_validator("style")
    @classmethod
    def validate_style(cls, v: str) -> str:
        """허용된 스타일인지 검증. 아니면 '기본'으로 폴백."""
        return v if v in VALID_STYLES else "기본"


class TextGenerationResponse(BaseModel):
    """광고 문구 생성 응답."""

    ad_copies: list[str] = Field(
        ...,
        min_length=1,
        description="광고 문구 목록 (기본 3개)",
    )
    promo_sentences: list[str] = Field(
        ...,
        min_length=1,
        description="확장형 홍보 문장 목록 (기본 2개)",
    )
    story_copies: list[str] = Field(
        default_factory=list,
        description="인스타그램 스토리용 초단문 카피 2~3개"
    )
