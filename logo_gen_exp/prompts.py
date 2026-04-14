"""로고 생성 프롬프트 빌더 — 순수 함수.

build_logo_generation_prompt(name, color_hex) 는 `brand_name` + 브랜드 색상만으로
gpt-image-1 같은 이미지 모델에 넘길 프롬프트 한 덩어리를 돌려준다.

원칙:
- ONLY text wordmark (일러스트·아이콘·배경·그림자·3D 금지)
- 순백 배경에 브랜드 색상 글자
- 컵·접시·포장에 인쇄 가능한 단순 벡터 스타일
- 한글 이름이면 한글(Hangul) 렌더링을 명시해 모델이 올바른 글자 모양을 그리도록 유도
"""

from __future__ import annotations

import re

# ── 언어 판정 ──
_HANGUL_PATTERN = re.compile(r"[\uAC00-\uD7A3]")

# ── 언어별 폰트 톤 ──
ENGLISH_FONT = "soft, rounded sans-serif typeface (friendly, not too thin, not too bold)"
KOREAN_FONT = "soft rounded Korean (Hangul) typeface, friendly and legible, not too thin, not too bold"

# ── 공통 금지 항목 ──
FORBIDDEN_ELEMENTS = (
    "No illustrations, no icons, no borders, no backgrounds other than pure white, "
    "no shadows, no 3D effects, no gradients, no textures."
)

# ── 인쇄 컨텍스트 ──
PRINTING_CONTEXT = (
    "Suitable for being printed on ceramic mugs, plates, paper bags, napkins, "
    "and packaging."
)


def _is_hangul(s: str) -> bool:
    """문자열에 한글(완성형) 이 하나라도 포함되면 True."""
    return bool(_HANGUL_PATTERN.search(s))


# ─────────────────────────────────────────────────────────────
# edit 모드 전용 (PIL 로 렌더한 베이스 로고를 AI 로 변형)
# ─────────────────────────────────────────────────────────────
_EDIT_PRESERVATION_CLAUSE = (
    "STRICT PRESERVATION (must keep):\n"
    "- The exact same letters and spelling of the existing wordmark.\n"
    "- Do NOT add, remove, or change any letter, number, or symbol.\n"
    "- Keep the text color solid and consistent (no gradients).\n"
    "- Background MUST remain pure white (#FFFFFF) — "
    "no textures, patterns, gradients, borders, or fills of any kind."
)

_EDIT_ALLOWED_SCOPE = (
    "ALLOWED CHANGES (typographic refinement ONLY — no background, no decoration):\n"
    "- Letter spacing (tighter / wider)\n"
    "- Letter weight (thinner / bolder)\n"
    "- Slant or italic style\n"
    "- Relative size of individual letters within the wordmark "
    "(per-letter size adjustment is allowed, e.g. making one letter bigger)\n"
    "- Overall position and scale of the wordmark within the canvas\n"
    "- Subtle stroke flourishes on the letters themselves\n"
    "\n"
    "FORBIDDEN (never produce these):\n"
    "- Any background texture, pattern, gradient, color fill, or border.\n"
    "- Any illustration, icon, plant, leaf, star, frame, or ornament.\n"
    "- Shadows, glows, 3D effects, bevels, or outlines around letters."
)

_EDIT_FOOTER = (
    "Output: square 1:1 image on pure white background (#FFFFFF). "
    "Only the wordmark text is visible; no other visual elements. "
    "The text must remain perfectly readable without distortion."
)


def build_edit_prompt(*, user_instruction: str) -> str:
    """PIL+AI edit 모드 전용 프롬프트 빌더.

    사용자 자유 지시에 "글자 보존" 가드를 둘러 모델이 장식/배경만 변형하도록 유도.
    빈 문자열 / 공백만 있는 입력은 ValueError 로 거부.
    """
    stripped = user_instruction.strip() if user_instruction else ""
    if not stripped:
        raise ValueError("edit 프롬프트가 비어 있습니다. user_instruction 을 제공하세요.")

    return (
        "You are editing a minimalist typographic wordmark logo.\n\n"
        f"{_EDIT_PRESERVATION_CLAUSE}\n\n"
        f"{_EDIT_ALLOWED_SCOPE}\n\n"
        "USER INSTRUCTION (apply within the allowed scope above):\n"
        f"{user_instruction}\n\n"
        f"{_EDIT_FOOTER}"
    )


def build_logo_generation_prompt(*, name: str, color_hex: str) -> str:
    """브랜드 이름·색상 → 이미지 모델용 로고 생성 프롬프트.

    Args:
        name: 브랜드 이름 (영문/한글/혼합 모두 허용).
        color_hex: "#RRGGBB" 형식의 색상 코드. 대소문자 그대로 보존.
    """
    font_instruction = KOREAN_FONT if _is_hangul(name) else ENGLISH_FONT

    return (
        "A minimalist typographic wordmark logo.\n"
        f'The logo shows ONLY the text: "{name}".\n'
        f"Typography: {font_instruction}.\n"
        f"Color: solid {color_hex} on pure white background.\n"
        "Flat vector style. Centered composition with generous negative space. "
        "Square 1:1 aspect ratio.\n"
        f"{FORBIDDEN_ELEMENTS}\n"
        f"{PRINTING_CONTEXT}"
    )
