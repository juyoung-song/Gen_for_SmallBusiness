"""build_edit_prompt 단위 테스트 (TDD 사이클 5 + 사이클 7 프롬프트 재설계).

PIL+AI edit 모드 전용 프롬프트 빌더.
- 사용자 자유 지시 포함
- 글자 보존 가드
- 배경 및 장식 변형 **전면 금지** (사이클 7)
- 타이포 속성(자간·굵기·기울기·개별 크기) 조정만 허용
"""

import pytest

from logo_gen_exp.prompts import build_edit_prompt


class TestUserInstruction:
    def test_includes_user_instruction_verbatim(self):
        p = build_edit_prompt(user_instruction="g만 크게")
        assert "g만 크게" in p

    def test_long_instruction_preserved(self):
        instr = "전체적으로 자간을 좁히고 굵기를 약간 굵게, 첫 글자만 기울임꼴."
        p = build_edit_prompt(user_instruction=instr)
        assert instr in p


class TestPreservationClause:
    def test_mentions_preserving_wordmark(self):
        p = build_edit_prompt(user_instruction="x").lower()
        assert "wordmark" in p or "text" in p
        assert "keep" in p or "preserv" in p

    def test_forbids_new_letters(self):
        p = build_edit_prompt(user_instruction="x").lower()
        assert "do not add" in p or "not add" in p
        assert "letter" in p or "text" in p or "spell" in p

    def test_forbids_distorting_or_changing_letters(self):
        p = build_edit_prompt(user_instruction="x").lower()
        # 왜곡/변경 금지가 어떤 식으로든 표현되어야 함
        assert "distort" in p or "change" in p or "do not remove" in p


class TestBackgroundAndDecorationForbidden:
    """사이클 7: 배경/장식 전면 금지 — '들쭉날쭉' 이 배경 웨이브로 나오는 문제 방지."""

    def test_mandates_pure_white_background(self):
        p = build_edit_prompt(user_instruction="x").lower()
        # 순백 배경 명시
        assert "pure white" in p
        assert "#ffffff" in p

    def test_forbids_background_textures_and_patterns(self):
        p = build_edit_prompt(user_instruction="x").lower()
        # texture / pattern / gradient / border 중 최소 3개 금지어로 등장
        for forbidden in ["texture", "pattern", "gradient", "border"]:
            assert forbidden in p, f"금지 키워드 '{forbidden}' 가 프롬프트에 없음"

    def test_forbids_decorations_and_icons(self):
        p = build_edit_prompt(user_instruction="x").lower()
        # 아이콘/장식/잎/프레임 등 중 3개 이상 금지어 포함
        hits = sum(
            w in p for w in ["illustration", "icon", "ornament", "frame", "leaf"]
        )
        assert hits >= 3, f"장식 관련 금지어가 충분하지 않음: 현재 {hits}"

    def test_forbids_shadows_glows_3d(self):
        p = build_edit_prompt(user_instruction="x").lower()
        assert "shadow" in p
        assert "glow" in p or "3d" in p


class TestAllowedScope:
    """사이클 7: 타이포 조정 키워드는 반드시 포함."""

    def test_mentions_letter_spacing_or_weight(self):
        p = build_edit_prompt(user_instruction="x").lower()
        hits = sum(
            w in p for w in ["letter spacing", "weight", "slant", "italic"]
        )
        assert hits >= 2, f"타이포 조정 키워드 부족: 현재 {hits}"

    def test_mentions_per_letter_size(self):
        """개별 글자 크기 조정 허용 명시 — 'g만 크게' 같은 지시 대응."""
        p = build_edit_prompt(user_instruction="x").lower()
        assert "individual" in p or "per-letter" in p or "size of" in p


class TestValidation:
    def test_empty_instruction_raises(self):
        with pytest.raises(ValueError):
            build_edit_prompt(user_instruction="")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError):
            build_edit_prompt(user_instruction="   \n\t  ")
