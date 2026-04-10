"""광고 목적 카테고리 6종 테스트 (design.md §4.1.1).

design.md 가 지정한 카테고리 6종:
1. 신메뉴 출시
2. 주말·시즌 한정
3. 할인·이벤트
4. 일상·감성
5. 영업 안내
6. 감사·안부

목적:
- 앱 전체에서 카테고리 목록을 단일 소스로 관리
- is_valid_category(name) 로 입력 검증
"""

from utils.goal_categories import (
    GOAL_CATEGORIES,
    is_valid_category,
)


class TestGoalCategories:
    def test_exactly_six_categories(self):
        assert len(GOAL_CATEGORIES) == 6

    def test_categories_match_design_md(self):
        assert GOAL_CATEGORIES == (
            "신메뉴 출시",
            "주말·시즌 한정",
            "할인·이벤트",
            "일상·감성",
            "영업 안내",
            "감사·안부",
        )

    def test_is_valid_category_returns_true_for_known(self):
        assert is_valid_category("신메뉴 출시") is True
        assert is_valid_category("감사·안부") is True

    def test_is_valid_category_returns_false_for_unknown(self):
        assert is_valid_category("아무말") is False
        assert is_valid_category("") is False

    def test_tuple_is_immutable(self):
        """외부 코드가 실수로 수정하지 못하도록 tuple 로 고정."""
        import pytest

        with pytest.raises((TypeError, AttributeError)):
            GOAL_CATEGORIES.append("추가")  # type: ignore[attr-defined]
