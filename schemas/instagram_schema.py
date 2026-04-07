"""인스타그램 캡션 및 업로드 관련 스키마."""
from pydantic import BaseModel

class CaptionGenerationRequest(BaseModel):
    product_name: str
    ad_copies: list[str]
    style: str
    brand_philosophy: str = ""
    is_new_product: bool = False
    is_renewal_product: bool = False
    attachment_count: int = 0

class CaptionGenerationResponse(BaseModel):
    caption: str
    hashtags: str
