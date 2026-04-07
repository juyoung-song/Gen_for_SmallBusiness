"""이미지 생성 입출력 스키마.

architecture.md 7.2 기준:
- ImageGenerationRequest: 사용자 입력 (프롬프트, 스타일)
- ImageGenerationResponse: 생성 결과 (이미지 바이너리, 프롬프트)
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from schemas.text_schema import VALID_STYLES


VALID_LOCAL_BACKENDS = {"ip_adapter", "img2img", "hybrid"}


class ImageInferenceOptions(BaseModel):
    """요청 단위로 덮어쓸 이미지 추론 설정."""

    use_local_model: bool | None = Field(
        default=None,
        description="True면 로컬 diffusers, False면 Hugging Face API 사용",
    )
    image_model: str | None = Field(
        default=None,
        description="Hugging Face API 모드에서 사용할 모델 ID",
    )
    local_sd15_model_id: str | None = Field(
        default=None,
        description="로컬 diffusers 모드에서 사용할 베이스 모델 ID",
    )
    local_backend: str | None = Field(
        default=None,
        description="로컬 diffusers 백엔드 (ip_adapter / img2img / hybrid)",
    )
    local_inference_steps: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description="로컬 diffusers 추론 스텝 수",
    )
    local_guidance_scale: float | None = Field(
        default=None,
        ge=0.0,
        le=20.0,
        description="로컬 diffusers guidance scale",
    )
    local_ip_adapter_scale: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="IP-Adapter scale",
    )
    local_img2img_strength: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="img2img strength",
    )
    local_ip_adapter_weight_name: str | None = Field(
        default=None,
        description="IP-Adapter 가중치 파일명",
    )

    @field_validator("local_backend")
    @classmethod
    def validate_backend(cls, value: str | None) -> str | None:
        """허용된 로컬 백엔드인지 검증."""
        if value is None:
            return value
        return value if value in VALID_LOCAL_BACKENDS else "ip_adapter"


class ReferenceImageContext(BaseModel):
    """보관함에서 선택한 참고 이미지와 메타데이터."""

    source: str = Field(default="history")
    label: str = Field(default="")
    history_id: str = Field(default="")
    generation_type: str = Field(default="")
    product_name: str = Field(default="")
    description: str = Field(default="")
    style: str = Field(default="")
    created_at: str = Field(default="")
    image_name: str = Field(default="")
    image_path: str = Field(default="")
    image_bytes: bytes | None = Field(default=None)
    revised_prompt: str = Field(default="")
    ad_copies: list[str] = Field(default_factory=list)
    promo_sentences: list[str] = Field(default_factory=list)


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
    brand_philosophy: str = Field(
        default="",
        description="브랜드 철학/핵심 가치",
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
    is_new_product: bool = Field(
        default=False,
        description="신상품 여부",
    )
    is_renewal_product: bool = Field(
        default=False,
        description="리뉴얼 상품 여부",
    )
    attachment_count: int = Field(
        default=0,
        ge=0,
        description="첨부 이미지 개수",
    )
    reference_analysis: str = Field(
        default="",
        description="선택한 참고 이미지들에 대한 GPT 분석 요약",
    )
    reference_contexts: list[ReferenceImageContext] = Field(
        default_factory=list,
        description="보관함에서 선택한 참고 이미지/메타데이터 목록",
    )
    inference_options: ImageInferenceOptions | None = Field(
        default=None,
        description="요청 단위 이미지 모델/추론 파라미터 override",
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
