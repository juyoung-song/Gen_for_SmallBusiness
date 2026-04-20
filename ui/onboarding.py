"""온보딩 화면 — Brand 최초 1회 설정.

docs/schema.md §3.1, docs/onboarding.md 흐름:
  1. 사용자 입력 (이름/로고/컬러 + 추구미 URL + 가게 설명 + 가게 분위기)
  2. "분석 시작" 버튼 → OnboardingService.generate_draft()
  3. 검수 화면 (타협 모드: "그대로 OK" 큰 버튼 + 작은 "수정하기")
  4. 확정 → OnboardingService.finalize() → Brand DB 저장 → 광고 화면으로 라우팅

본 파일은 Streamlit UI 만 담당한다. 비즈니스 로직은 services/onboarding_service.py.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from backends.insta_capture import InstaCaptureBackend
from config.database import AsyncSessionLocal
from services.brand_service import BrandService
from services.logo_service import LogoAutoGenerator
from services.onboarding_service import (
    BrandDraft,
    GPTVisionAnalyzer,
    OnboardingService,
)
from utils.async_runner import run_async


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ONBOARDING_DIR = _PROJECT_ROOT / "data" / "onboarding"
# CP14: 로고 자동 생성용 폰트 / 저장 디렉토리.
_LOGO_FONT_PATH = _PROJECT_ROOT / "assets" / "fonts" / "LXGWWenKaiKR-Medium.ttf"
_BRAND_ASSETS_DIR = _PROJECT_ROOT / "data" / "brand_assets"


def render_onboarding_screen(settings) -> None:
    st.title("🎨 브랜드 첫 세팅")
    st.info(
        "🍞 이 서비스는 **카페·베이커리·디저트 가게 사장님**을 위한 도구입니다.\n\n"
        "앞으로 모든 광고가 **같은 브랜드 톤**으로 만들어지도록, "
        "딱 한 번만 우리 가게의 정체성을 알려주세요."
    )

    if "onboarding_draft" not in st.session_state:
        st.session_state.onboarding_draft = None

    draft: BrandDraft | None = st.session_state.onboarding_draft

    if draft is None:
        _render_input_stage(settings)
    else:
        _render_review_stage(settings, draft)


def _render_input_stage(settings) -> None:
    """1단계: 브랜드 기본 정보 + 자유 서술 + 추구미 레퍼런스 3섹션 입력."""
    with st.container(border=True):
        st.markdown("### 1️⃣ 브랜드 기본 정보 🎨")

        brand_name = st.text_input(
            "🏢 브랜드 이름 (필수)",
            placeholder="예: 구름 베이커리",
            key="onboarding_brand_name",
        )

        col_color, col_atmo = st.columns(2)
        with col_color:
            brand_color = st.color_picker(
                "🎨 브랜드 대표 색상",
                value=st.session_state.get("onboarding_brand_color", "#5562EA"),
                key="onboarding_brand_color",
            )
        with col_atmo:
            brand_mood = st.text_input(
                "🌿 브랜드 분위기 (한 줄)",
                placeholder="예: 따뜻하고 단정한, 모던한 내추럴",
                key="onboarding_brand_mood",
            )

        brand_logo_file = st.file_uploader(
            "📥 브랜드 로고 (선택)",
            type=["png", "jpg", "jpeg"],
            key="onboarding_brand_logo",
        )

    with st.container(border=True):
        st.markdown("### 2️⃣ 우리 가게 상세 소개")
        description = st.text_area(
            "어떤 가게인가요? 자유롭게 써주세요.",
            placeholder=(
                "예: 동네에서 작은 베이커리를 운영하고 있어요. 매일 아침 막 구운 "
                "유럽식 캄파뉴와 크루아상을 팝니다. 따뜻하고 단정한 분위기를 좋아하고, "
                "원색보다 베이지/브라운/우드 톤이 잘 어울려요. 손님은 주로 동네 직장인과 "
                "20-30대 주부예요."
            ),
            height=180,
            key="onboarding_description",
        )

    with st.container(border=True):
        st.markdown("### 3️⃣ 추구미 인스타 프로필")
        st.caption(
            "벤치마크하고 싶은 인스타 계정의 프로필 URL 을 넣어주세요. "
            "AI 가 자동으로 피드를 살펴보고 톤·색감·사진 스타일을 분석합니다. "
            "💡 꼭 카페/베이커리 계정이 아니어도 됩니다. 다른 업종이면 카테고리는 "
            "그대로 카페/베이커리/디저트로 두고 톤만 참고해요."
        )
        instagram_url = st.text_input(
            "인스타 프로필 URL",
            placeholder="https://www.instagram.com/some_reference/",
            key="onboarding_instagram_url",
        )

    st.write("")

    required_ok = bool(
        brand_name.strip()
        and description.strip()
        and instagram_url.strip()
        and brand_mood.strip()
    )

    if st.button(
        "🔍 분석 시작 (1~2분 소요)",
        type="primary",
        width="stretch",
        disabled=not required_ok,
    ):
        with st.status("브랜드 분석 중...", expanded=True) as status:
            try:
                brand_logo_path: str | None = None
                if brand_logo_file is not None:
                    from pathlib import Path as _Path

                    from utils.staging_storage import save_to_brand_assets
                    ext = _Path(brand_logo_file.name).suffix.lower() or ".png"
                    saved = save_to_brand_assets(
                        brand_logo_file.getvalue(), extension=ext
                    )
                    brand_logo_path = str(saved)
                    st.write(f"📥 로고 저장됨 → {saved.name}")

                st.write("📸 인스타 프로필 캡처 중...")
                capture = InstaCaptureBackend()
                analyzer = GPTVisionAnalyzer(settings)
                service = OnboardingService(
                    capture_backend=capture,
                    vision_analyzer=analyzer,
                    onboarding_dir=_ONBOARDING_DIR,
                )

                st.write("🧠 GPT 가 브랜드 톤을 정리하는 중...")
                draft = run_async(
                    service.generate_draft(
                        name=brand_name.strip(),
                        color_hex=brand_color,
                        logo_path=brand_logo_path,
                        input_instagram_url=instagram_url.strip(),
                        input_description=description.strip(),
                        input_mood=brand_mood.strip(),
                    )
                )
                st.session_state.onboarding_draft = draft
                status.update(
                    label="분석 완료! 아래에서 확인해주세요.",
                    state="complete",
                )
                st.rerun()
            except Exception as e:
                status.update(label="❌ 분석 실패", state="error")
                st.error(f"분석 중 오류가 발생했습니다: {e}")
                st.exception(e)


def _render_review_stage(settings, draft: BrandDraft) -> None:
    """2단계: 검수 (타협 모드 — OK 버튼 크게, 수정 버튼 작게)."""
    st.markdown("### 📝 이렇게 정리했어요")
    st.caption("AI 가 사용자 설명과 인스타 프로필을 종합해 만든 '우리 브랜드 설명' 입니다.")

    edit_mode = st.session_state.get("onboarding_edit_mode", False)

    if edit_mode:
        edited = st.text_area(
            "브랜드 설명 (자유롭게 수정하세요)",
            value=draft.style_prompt,
            height=300,
            key="onboarding_edited_style_prompt",
        )
        col_save, col_cancel = st.columns([1, 1])
        with col_save:
            if st.button("💾 수정 저장", type="primary", width="stretch"):
                st.session_state.onboarding_draft = draft.with_edited_style_prompt(edited)
                st.session_state.onboarding_edit_mode = False
                st.rerun()
        with col_cancel:
            if st.button("↩️ 취소", width="stretch"):
                st.session_state.onboarding_edit_mode = False
                st.rerun()
    else:
        with st.container(border=True):
            st.markdown(draft.style_prompt)

        st.write("")
        col_ok, col_edit = st.columns([3, 1])
        with col_ok:
            if st.button(
                "👍 이대로 확정하기",
                type="primary",
                width="stretch",
            ):
                _persist_draft(settings, draft)
        with col_edit:
            if st.button("✏️ 수정하기", width="stretch"):
                st.session_state.onboarding_edit_mode = True
                st.rerun()

        st.write("")
        if st.button("🔁 처음부터 다시", type="secondary"):
            st.session_state.onboarding_draft = None
            st.session_state.onboarding_edit_mode = False
            st.rerun()


def _persist_draft(settings, draft: BrandDraft) -> None:
    """draft 를 Brand 로 DB 저장하고 앱을 광고 생성 화면으로 라우팅."""

    async def _save() -> None:
        async with AsyncSessionLocal() as session:
            brand_service = BrandService(session)
            # 로고 미업로드 시 PIL 폰트 렌더링으로 자동 생성 (CP14).
            logo_generator = LogoAutoGenerator(
                font_path=_LOGO_FONT_PATH,
                save_dir=_BRAND_ASSETS_DIR,
            )
            service = OnboardingService(
                capture_backend=InstaCaptureBackend(),  # 재사용 없음
                vision_analyzer=GPTVisionAnalyzer(settings),  # 재사용 없음
                onboarding_dir=_ONBOARDING_DIR,
                brand_service=brand_service,
                logo_generator=logo_generator,
            )
            await service.finalize(draft)

    try:
        run_async(_save())
    except Exception as e:
        st.error(f"저장 중 오류가 발생했습니다: {e}")
        return

    st.success("🎉 브랜드 설정이 완료되었습니다!")
    st.session_state.onboarding_draft = None
    st.session_state.onboarding_edit_mode = False
    st.session_state.onboarding_done = True
    st.balloons()
    st.rerun()
