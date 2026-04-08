"""광고 목적 카테고리 6종 — 단일 소스 (design.md §4.1.1).

광고 생성 폼의 "광고 목적" 섹션은 아래 6종 칩 + 자유 텍스트 입력란으로 구성된다.
카테고리 목록은 본 모듈에서 한 번만 정의되고, UI / 프롬프트 빌더 / 검증 로직 모두
여기를 import 해서 사용한다.
"""

GOAL_CATEGORIES: tuple[str, ...] = (
    "신메뉴 출시",
    "주말·시즌 한정",
    "할인·이벤트",
    "일상·감성",
    "영업 안내",
    "감사·안부",
)


def is_valid_category(name: str) -> bool:
    """입력된 문자열이 유효한 광고 목적 카테고리인지 확인."""
    return name in GOAL_CATEGORIES
