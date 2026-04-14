"""logo_gen_exp 테스트 전용 fixtures 와 상수."""

from pathlib import Path

# 실험 폴더 루트
_EXP_ROOT = Path(__file__).resolve().parent.parent

# 기본 한글 지원 붓글씨풍 폰트 — 워드마크에 어울리는 부드러운 톤
FONT_PATH_KR_MEDIUM = _EXP_ROOT / "LXGWWenKaiKR-Medium.ttf"
FONT_PATH_KR_REGULAR = _EXP_ROOT / "LXGWWenKaiKR-Regular.ttf"
