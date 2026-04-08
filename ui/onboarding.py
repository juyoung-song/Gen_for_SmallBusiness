"""온보딩 화면 — brand_image 최초 1회 설정.

design.md §3 흐름:
  1. 사용자 자유 텍스트 + 인스타 프로필 URL 입력
  2. "분석 시작" 버튼 → OnboardingService.generate_draft()
  3. 검수 화면 (타협 모드: "그대로 OK" 큰 버튼 + 작은 "수정하기")
  4. 확정 → OnboardingService.finalize() → DB 저장 → 광고 화면으로 라우팅

본 파일은 Streamlit UI 만 담당한다. 비즈니스 로직은 services/onboarding_service.py.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from backends.insta_capture import InstaCaptureBackend
from config.database import AsyncSessionLocal
from services.brand_image_service import BrandImageService
from services.onboarding_service import (
    BrandImageDraft,
    GPTVisionAnalyzer,
    OnboardingService,
)
from utils.async_runner import run_async


_ONBOARDING_DIR = Path(__file__).resolve().parent.parent / "data" / "onboarding"


def render_onboarding_screen(settings) -> None:
    """온보딩 화면 전체를 렌더링한다."""
    st.title("🎨 브랜드 첫 세팅")
    st.markdown(
        "앞으로 모든 광고가 **같은 브랜드 톤**으로 만들어지도록, "
        "딱 한 번만 브랜드 정체성을 알려주세요."
    )

    # 세션 상태 초기화
    if "onboarding_draft" not in st.session_state:
        st.session_state.onboarding_draft = None

    draft: BrandImageDraft | None = st.session_state.onboarding_draft

    if draft is None:
        _render_input_stage(settings)
    else:
        _render_review_stage(settings, draft)


def _render_input_stage(settings) -> None:
    """1단계: 자유 텍스트 + 인스타 URL 입력."""
    with st.container(border=True):
        st.markdown("### 1️⃣ 브랜드 소개")
        freetext = st.text_area(
            "어떤 브랜드인가요? 자유롭게 써주세요.",
            placeholder="예: 조용한 동네에서 운영하는 작은 베이커리예요. 따뜻하고 단순한 분위기를 좋아합니다. 원색보다는 베이지/브라운 톤이 어울려요.",
            height=150,
            key="onboarding_freetext",
        )

        st.markdown("### 2️⃣ 추구미 인스타 프로필")
        st.caption(
            "벤치마크하고 싶은 인스타 계정의 프로필 URL 을 넣어주세요. "
            "AI 가 자동으로 피드를 살펴보고 브랜드 톤을 분석합니다."
        )
        instagram_url = st.text_input(
            "인스타 프로필 URL",
            placeholder="https://www.instagram.com/some_reference/",
            key="onboarding_instagram_url",
        )

    st.write("")
    if st.button(
        "🔍 분석 시작 (1~2분 소요)",
        type="primary",
        width="stretch",
        disabled=not (freetext.strip() and instagram_url.strip()),
    ):
        with st.status("브랜드 분석 중...", expanded=True) as status:
            try:
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
                        freetext=freetext.strip(),
                        instagram_url=instagram_url.strip(),
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


def _render_review_stage(settings, draft: BrandImageDraft) -> None:
    """2단계: 검수 (타협 모드 — OK 버튼 크게, 수정 버튼 작게)."""
    st.markdown("### 📝 이렇게 정리했어요")
    st.caption("AI 가 사용자 설명과 인스타 프로필을 종합해 만든 '우리 브랜드 설명' 입니다.")

    # 수정 가능한 텍스트 영역
    edit_mode = st.session_state.get("onboarding_edit_mode", False)

    if edit_mode:
        edited = st.text_area(
            "브랜드 설명 (자유롭게 수정하세요)",
            value=draft.content,
            height=300,
            key="onboarding_edited_content",
        )
        col_save, col_cancel = st.columns([1, 1])
        with col_save:
            if st.button("💾 수정 저장", type="primary", width="stretch"):
                st.session_state.onboarding_draft = draft.with_edited_content(edited)
                st.session_state.onboarding_edit_mode = False
                st.rerun()
        with col_cancel:
            if st.button("↩️ 취소", width="stretch"):
                st.session_state.onboarding_edit_mode = False
                st.rerun()
    else:
        with st.container(border=True):
            st.markdown(draft.content)

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


def _persist_draft(settings, draft: BrandImageDraft) -> None:
    """draft 를 DB 에 저장하고 앱을 광고 생성 화면으로 라우팅."""

    async def _save() -> None:
        async with AsyncSessionLocal() as session:
            brand_service = BrandImageService(session)
            service = OnboardingService(
                capture_backend=InstaCaptureBackend(),  # 재사용 없음
                vision_analyzer=GPTVisionAnalyzer(settings),  # 재사용 없음
                onboarding_dir=_ONBOARDING_DIR,
                brand_image_service=brand_service,
            )
            await service.finalize(draft, user_id="default")

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
