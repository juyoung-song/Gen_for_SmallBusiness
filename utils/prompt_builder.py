"""프롬프트 생성 유틸리티.

architecture.md 4.4 기준:
- 사용자 입력 → AI 프롬프트 변환
- 스타일별 프롬프트 템플릿 관리
- 순수 함수, 상태 없음
"""


# ──────────────────────────────────────────────
# 스타일별 톤앤매너 매핑
# ──────────────────────────────────────────────
_STYLE_GUIDE: dict[str, str] = {
    "기본": "가장 깔끔하고 이해하기 쉽게 작성하세요.",
    "감성": "따뜻하고 부드러운 말투로, 감정에 호소하는 문구를 작성하세요.",
    "고급": "격식 있고 우아한 말투로, 럭셔리한 느낌의 문구를 작성하세요.",
    "유머": "재밌고 센스 있는 말투로, 웃음을 자아내는 문구를 작성하세요.",
    "심플": "짧고 핵심만 간단하게 전달하는 문구를 작성하세요.",
}

# gpt-image-1 전용 전문 사진작가 촬영 디렉션
_IMAGE_STYLE_DIRECTIVE: dict[str, str] = {
    "기본": (
        "Commercial Standard: Clean, balanced setup with eye-level perspective. "
        "High-quality diffused lighting, neutral textures, and professional focus on product details."
    ),
    "감성": (
        "Sentimental Lifestyle: Warm, soft-focus photography. "
        "Side natural window light, shallow depth of field with creamy bokeh, "
        "and cozy, inviting morning mood."
    ),
    "고급": (
        "Premium Noir: Moody, high-contrast photography. "
        "Dramatic chiaroscuro lighting, deep-toned matte backgrounds, "
        "and extreme focus on the premium material and surface detail."
    ),
    "유머": (
        "Pop & Playful: High-energy pop photography. "
        "Vibrant saturated colors, hard direct flash with sharp shadows, "
        "and dynamic diagonal overhead arrangement."
    ),
    "심플": (
        "Ultimate Minimalism: Austere product portrait. "
        "Solid monochromatic background, shadowless soft lighting, "
        "centered composition with ample negative space."
    ),
}


# ──────────────────────────────────────────────
# 레퍼런스 기반 정교화 레이어 (스타벅스/투썸/할리스)
# ──────────────────────────────────────────────
_BRAND_CUES = (
    "- 브랜드 톤앤매너: 감성적인 도입부 + 명확한 핵심 정보 (군더더기 배제)\n"
    "- 분위기: 과한 광고(예: 파격 세일!) 보다는 일상의 소소한 행복, 취향, 경험을 자극할 것\n"
    "- 문장 스타일: 정돈된 브랜드 문장처럼 작성할 것\n"
    "- 이미지 가이드: 제품 중심의 여백 미, 자연스러운 빛 활용 강조\n"
)

def _product_status_prompt(is_new_product: bool) -> str:
    """상품 상태에 따른 프롬프트 지침 (Loah 이식)."""
    if is_new_product:
        return "이번 대상은 신상품입니다. 첫 공개의 신선함, 기대감, 런칭 포인트를 분명히 드러내세요."
    return "이번 대상은 기존 상품입니다. 이미 검증된 매력과 완성도, 신뢰감을 중심으로 표현하세요."


def _product_status_label(is_new_product: bool) -> str:
    return "신상품" if is_new_product else "기존 상품"


def build_text_prompt(
    product_name: str,
    description: str,
    style: str,
    goal: str = "일반 홍보",
    image_hint: str = None,
    brand_prompt: str = "",
    is_new_product: bool = False,
    reference_analysis: str = "",
) -> tuple[str, str]:
    """광고 문구 생성을 위한 프롬프트를 반환합니다.

    Loah 프롬프트 이식 — 상품 상태 분기 + reference_analysis 반영 추가.
    """
    style_instruction = _STYLE_GUIDE.get(style, _STYLE_GUIDE["기본"])
    product_status_instruction = _product_status_prompt(is_new_product)

    image_context = ""
    if image_hint:
        image_context = (
            f"업로드 이미지 특징: {image_hint}\n"
            "업로드 이미지의 색감, 분위기, 제품 인상을 문구에 자연스럽게 참고하세요.\n"
        )

    # Step A: 사용자별 brand_image 가 있으면 그걸, 없으면 하드코딩 기본값
    if brand_prompt.strip():
        brand_section = brand_prompt.strip()
    else:
        brand_section = _BRAND_CUES

    reference_context = ""
    if reference_analysis.strip():
        reference_context = (
            f"참고 이미지 분석 요약: {reference_analysis.strip()}\n"
            "이 요약에서 드러난 분위기, 색감, 제품 프레이밍, 브랜드 단서를 "
            "문구의 장면감과 어휘에 자연스럽게 반영하세요.\n"
        )

    system_prompt = (
        "당신은 대한민국 최고의 브랜드 전략가이자 카피라이터입니다.\n"
        f"현재 프로젝트의 핵심 홍보 목적은 [{goal}] 입니다.\n"
        "모든 생성 결과물은 반드시 이 목적을 최우선으로 달성해야 합니다.\n"
        "반드시 한국어로 작성하세요.\n\n"
        f"[[브랜드 가이드라인]]\n{brand_section}\n\n"
        f"[[상품 상태 지침]]: {product_status_instruction}\n"
        f"[[글 톤 지침]]: {style_instruction}\n\n"
        "중요 규칙:\n"
        "1. 모든 문구는 사용자가 제시한 [홍보 목적]에 부합해야 합니다.\n"
        "2. 모든 문구는 반드시 위 [[브랜드 가이드라인]]과 일치하는 톤으로 작성해야 합니다.\n"
        "3. [홍보 문장] 섹션은 절대 짧게 쓰지 마세요. 각 항목은 반드시 2문장 이상이어야 합니다.\n"
        "4. [스토리 카피]는 가장 짧고 강력한 Hook으로 작성하되, 전체 홍보 목적을 내포해야 합니다.\n"
        "5. 각 섹션은 길이와 목적이 서로 달라야 합니다.\n"
        "- [광고 문구]는 짧고 임팩트 있게\n"
        "- [홍보 문장]은 충분히 길고 설명적으로\n"
        "- [스토리 카피]는 가장 짧고 훅 중심으로 작성하세요."
    )

    user_prompt = (
        f"상품명: {product_name}\n"
        f"상품 설명: {description}\n"
        f"상품 상태: {_product_status_label(is_new_product)}\n"
        f"홍보 목적: {goal}\n"
        f"{reference_context}"
        f"{image_context}\n"
        "위 정보를 바탕으로 아래 세 가지 섹션을 작성하세요. "
        "홍보 목적 달성과 상세한 설명이 가장 중요합니다.\n\n"

        "1. [광고 문구]\n"
        "- 피드 게시물용 한 줄 카피 3개\n"
        "- 목적이 드러나는 짧고 임팩트 있는 문장\n\n"

        "2. [홍보 문장]\n"
        "- SNS/블로그 상세 설명 2개\n"
        "- 반드시 각 항목을 2~3문장으로 작성\n"
        "- 상품의 특징, 장점, 분위기, 사용/섭취 경험을 자연스럽게 풀어 설명\n"
        "- 절대 한 줄 카피처럼 짧게 쓰지 말 것\n\n"

        "3. [스토리 카피]\n"
        "- 스토리용 초단문 Hook 3개\n"
        "- 짧지만 목적이 느껴져야 함\n"
        "- 불필요한 설명 금지\n\n"

        "응답 형식:\n"
        "[광고 문구]\n"
        "1. ...\n"
        "2. ...\n"
        "3. ...\n\n"
        "[홍보 문장]\n"
        "1. 첫 번째 문장입니다. 두 번째 문장으로 이어집니다. 필요하면 세 번째 문장까지 작성합니다.\n"
        "2. 첫 번째 문장입니다. 두 번째 문장으로 이어집니다. 필요하면 세 번째 문장까지 작성합니다.\n\n"
        "[스토리 카피]\n"
        "1. ...\n"
        "2. ...\n"
        "3. ..."
    )

    return system_prompt, user_prompt


def build_image_prompt(
    product_name: str,
    description: str,
    style: str,
    goal: str = "일반 홍보",
    ad_copy: str = "",
    has_reference: bool = False,
    brand_prompt: str = "",
    is_new_product: bool = False,
    reference_analysis: str = "",
) -> str:
    """gpt-image-1 최적화 비주얼 컨셉 지시서를 생성합니다.
    
    SD/FLUX 방식의 키워드 번역을 폐기하고,
    gpt-image-1이 이해하는 자연어 명령문 형태로 재구성합니다.
    스타일 디렉션이 핵심 축이며, 브랜드 가이드라인이 보조합니다.
    """
    # 전문 사진작가 촬영 디렉션 (5대 스타일)
    style_directive = _IMAGE_STYLE_DIRECTIVE.get(style, _IMAGE_STYLE_DIRECTIVE["기본"])
    product_status = _product_status_label(is_new_product)

    brand_section = ""
    if brand_prompt.strip():
        brand_section = f"[Brand Guidelines — MUST follow]: {brand_prompt.strip()}\n\n"

    composition_section = ""
    if reference_analysis.strip():
        composition_section = (
            f"[Composition Guideline from Reference]: {reference_analysis.strip()}\n"
            "Strictly apply only the camera angle, lens distance, and subject placement "
            "described above. Ignore the color and subject matter of the reference.\n\n"
        )

    product_status_guide = (
        "Emphasize the novelty, first-reveal anticipation, and launch energy. "
        if is_new_product
        else "Emphasize trusted quality, signature appeal, and established brand confidence. "
    )

    return (
        f"{brand_section}"
        f"{composition_section}"
        f"[Product]: '{product_name}' — {product_status}. "
        f"{product_status_guide}"
        f"[Photography Style Directive]: {style_directive} "
        "[Output rules]: High-resolution commercial photography, no floating text or "
        "decorative overlays on the background. No text on image. "
        "Cinematic quality, ultra-sharp product focus."
    )
