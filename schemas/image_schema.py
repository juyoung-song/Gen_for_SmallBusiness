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
        description="상품 raw 이미지 (화장 전). 신상품 업로드 또는 기존 상품의 DB raw 이미지.",
    )
    reference_image_paths: list[str] = Field(
        default_factory=list,
        description=(
            "참조 이미지 풀(화장 후)에서 사용자가 선택한 파일 경로 리스트. "
            "각 경로는 generated_upload.image_path 에서 온 것이며, "
            "백엔드가 지원하면 다중 참조, 지원 안 하면 첫 장만 사용."
        ),
    )
    brand_prompt: str = Field(
        default="",
        description=(
            "온보딩 단계에서 생성된 brand_image.txt 본문. "
            "모든 이미지 생성 호출에 system prompt 로 주입된다 (design.md §2.3)."
        ),
    )
    is_new_product: bool = Field(
        default=False,
        description="신상품 여부 — 이미지 프롬프트에 런칭 에너지/신선함 반영",
    )
    reference_analysis: str = Field(
        default="",
        description="참조 이미지 분석 텍스트. 시각적 합성의 1차 참고 자료.",
    )
    logo_path: str | None = Field(
        default=None,
        description=(
            "브랜드 로고 PNG 파일 경로 (brand.logo_path). "
            "OpenAIImageBackend 가 multi-input 으로 함께 모델에 주입할 때 사용. "
            "그 외 백엔드(HF/Mock)는 무시 가능."
        ),
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
