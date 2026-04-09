"""build_image_prompt 의 goal_visual_map 회귀 테스트 (H1).

Step 1.4 에서 GOAL_CATEGORIES 를 6종 신규 라벨로 교체했으나
build_image_prompt 내부 goal_visual_map 은 구 라벨 키 그대로 남아서
모든 입력이 fallback "Clean, commercial grade product photography" 로만
선택되는 조용한 회귀 버그가 있었다. 본 테스트가 각 신규 카테고리가
고유한 visual strategy 에 매핑됨을 보장한다.
"""

from utils.goal_categories import GOAL_CATEGORIES
from utils.prompt_builder import build_image_prompt

_GENERIC_FALLBACK = "Clean, commercial grade product photography"


class TestGoalVisualMap:
    def test_all_six_categories_have_dedicated_visual_strategy(self):
        """GOAL_CATEGORIES 6종 모두 fallback 이 아닌 고유 전략으로 매핑."""
        strategies = {}
        for goal in GOAL_CATEGORIES:
            prompt = build_image_prompt(
                product_name="무화과 케이크",
                description="존맛",
                style="기본",
                goal=goal,
            )
            strategies[goal] = prompt

        # 어느 것도 fallback 만 쓰지 않아야 함
        for goal, prompt in strategies.items():
            assert _GENERIC_FALLBACK not in prompt, (
                f"'{goal}' 가 fallback 전략으로 떨어짐 — goal_visual_map 에 키 누락"
            )

    def test_each_category_has_distinct_strategy(self):
        """각 카테고리는 서로 다른 문장으로 프롬프트를 만든다."""
        prompts = set()
        for goal in GOAL_CATEGORIES:
            p = build_image_prompt(
                product_name="무화과 케이크",
                description="존맛",
                style="기본",
                goal=goal,
            )
            prompts.add(p)
        # 중복이 없어야 함 (6개 모두 고유)
        assert len(prompts) == len(GOAL_CATEGORIES)

    def test_unknown_goal_falls_back(self):
        """알 수 없는 goal 은 fallback 유지."""
        prompt = build_image_prompt(
            product_name="무화과 케이크",
            description="...",
            style="기본",
            goal="알 수 없는 카테고리",
        )
        assert _GENERIC_FALLBACK in prompt
