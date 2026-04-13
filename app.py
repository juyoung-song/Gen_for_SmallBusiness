"""생성형 AI 기반 광고 콘텐츠 제작 서비스 — 메인 엔트리포인트 (구조 리팩토링).

API 연동 및 데이터베이스(히스토리) 완성:
- SQLite & SQLAlchemy를 통한 비동기 생성 내역 저장/조회
- 멀티 탭 구조 (새로 만들기 / 아카이브) 지원

실행: streamlit run app.py
"""

import asyncio
import logging
import os
from pathlib import Path

import streamlit as st

logger = logging.getLogger(__name__)

from config.database import AsyncSessionLocal, init_db
from config.settings import get_settings, setup_logging
from ui.instagram_connect import render_instagram_connection
from ui.onboarding import render_onboarding_screen
from ui.reference_gallery import render_reference_gallery
from ui.sidebar import render_sidebar_settings
from schemas.image_schema import ImageGenerationRequest
from schemas.text_schema import TextGenerationRequest
from services.brand_service import BrandService
from services.generation_service import GenerationService, OutputSpec
from services.image_service import ImageService, ImageServiceError
from services.text_service import TextService, TextServiceError
from services.upload_service import UploadService
from utils.async_runner import run_async
from utils.goal_categories import GOAL_CATEGORIES
from utils.staging_storage import save_to_staging

# ══════════════════════════════════════════════
# 페이지 설정 (반드시 최상단에서 1회만 호출)
# ══════════════════════════════════════════════
st.set_page_config(
    page_title="사장님을 위한 AI 홍보 도우미",
    page_icon="✨",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ══════════════════════════════════════════════
# 글로벌 Custom CSS 주입
# ══════════════════════════════════════════════
st.markdown("""
<style>
.title-gradient {
    background: -webkit-linear-gradient(45deg, #FF6B6B, #5562EA);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800;
    font-size: 2.5rem;
    padding-bottom: 0.2rem;
    text-align: center;
}
.subtitle {
    color: #6c757d;
    font-size: 1.1rem;
    margin-bottom: 2rem;
    text-align: center;
    font-weight: 500;
}
.step-badge {
    background: linear-gradient(135deg, #6c5ce7, #a29bfe);
    color: white;
    font-weight: 900;
    border-radius: 50%;
    width: 26px;
    height: 26px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    margin-right: 8px;
    font-size: 13px;
    box-shadow: 0 2px 4px rgba(108, 92, 231, 0.3);
}
.ig-mock-header {
    display:flex; 
    align-items:center; 
    padding-bottom:12px; 
    border-bottom:1px solid #efefef;
    margin-bottom: 12px;
}
.ig-avatar {
    width:36px; 
    height:36px; 
    border-radius:50%; 
    background: linear-gradient(45deg, #f09433, #dc2743, #bc1888); 
    margin-right:12px;
}
.ig-username {
    font-weight: bold; 
    font-size:14px;
    color: #262626;
}
.ig-sponsored {
    font-size:11px; 
    color:#8e8e8e;
}
div[data-testid="stMarkdownContainer"] h4 {
    margin-top: 0;
    padding-top: 0;
}
/* st.code(코드블록)을 어떠한 박스나 테두리 없이 완전히 일반 글씨처럼 위장 (복사버튼만 둥둥 떠있게) */
div[data-testid="stCodeBlock"] > div {
    background-color: transparent !important;
}
div[data-testid="stCodeBlock"] {
    background-color: transparent !important;
    border: none !important;
    margin-bottom: 0.5rem !important;
}
div[data-testid="stCodeBlock"] pre {
    padding: 0 !important;
}
div[data-testid="stCodeBlock"] pre code {
    font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', 'Pretendard', sans-serif !important;
    font-size: 15px !important;
    color: #333333 !important;
    white-space: pre-wrap !important;
    background-color: transparent !important;
}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════
# 설정 및 DB 초기화
# ══════════════════════════════════════════════
settings = get_settings()
setup_logging(settings)
render_sidebar_settings(settings)
text_service = TextService(settings)
image_service = ImageService(settings)

# DB 테이블은 매 rerun 마다 idempotent 하게 보장 (캐시하지 않음).
# 이전에 @st.cache_resource 로 캐시했을 때, 모델 스키마가 바뀌어도 캐시
# 때문에 새 테이블이 생성되지 않아 OperationalError 가 발생했다.
# init_db() 의 Base.metadata.create_all 은 이미 있는 테이블은 skip 하므로
# 매 호출이 빠르게 no-op 이 된다.
asyncio.run(init_db())

# ══════════════════════════════════════════════
# Session State 초기화 (명확한 분리)
# ══════════════════════════════════════════════
_DEFAULT_STATE: dict = {
    # 1. 입력부 세션 관리
    "product_name": "",
    "product_description": "",
    "product_image": None,
    "generation_type": "글 + 사진 함께 만들기",
    "ad_purpose": "신상품 홍보",
    "text_tone": "기본",
    "image_style": "기본",
    
    # 2. 결과부 세션 관리
    "text_result": None,
    "image_result": None,
    "caption_result": None,
    "story_result": None, # 스토리용 합성 이미지 바이너리
    "story_text": "", # 선택된 스토리 카피
    "error_message": None,
    "error_exception": None,
    "last_request": None,
    "history_captions": {},
}
for key, default in _DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ══════════════════════════════════════════════
# 온보딩 라우팅 + brand 본문 로드
# ══════════════════════════════════════════════
# Brand 가 DB 에 없으면 온보딩 화면만 렌더하고 조기 return.
# 존재하면 style_prompt + name/color 프리픽스를 합쳐 session_state 에 캐시한다.
# 이후 광고 생성 시 request.brand_prompt 로 주입된다.
async def _load_brand():
    """온보딩된 Brand 객체를 통째 반환 (없으면 None)."""
    async with AsyncSessionLocal() as session:
        service = BrandService(session)
        return await service.get_first()


def _compose_brand_prompt(
    *, style_prompt: str, brand_name: str | None, brand_color: str | None
) -> str:
    """구조화 필드 (name/color_hex) 를 style_prompt 앞에 프리픽스로 합친다."""
    prefix_lines: list[str] = []
    if brand_name:
        prefix_lines.append(f"브랜드 이름: {brand_name}")
    if brand_color:
        prefix_lines.append(f"브랜드 대표 색상: {brand_color}")
    if not prefix_lines:
        return style_prompt
    return "\n".join(prefix_lines) + "\n\n" + style_prompt


_loaded_brand = run_async(_load_brand())
if _loaded_brand is None:
    render_onboarding_screen(settings)
    st.stop()

st.session_state.brand_prompt = _compose_brand_prompt(
    style_prompt=_loaded_brand.style_prompt,
    brand_name=_loaded_brand.name,
    brand_color=_loaded_brand.color_hex,
)
# _save_generation_record 가 꺼내쓸 수 있도록 Brand 객체 자체도 보관
st.session_state._current_brand = _loaded_brand

# 사이드바 인스타 연결 UI — Brand 를 넘긴다.
render_instagram_connection(settings, brand=_loaded_brand)


# ══════════════════════════════════════════════
# UI 매핑용 딕셔너리
# ══════════════════════════════════════════════
# S-3: TONE 과 STYLE 의 표시 맵이 완전히 동일하므로 단일 상수로 통합.
# 톤(텍스트)과 스타일(이미지) 양쪽에서 재사용.
TONE_STYLE_DISPLAY_MAP = {
    "기본 (가장 깔끔하게)": "기본",
    "감성 (따뜻하고 부드럽게)": "감성",
    "고급 (격식있고 우아하게)": "고급",
    "유머 (재밌고 센스있게)": "유머",
    "심플 (핵심만 간단하게)": "심플",
}

# 광고 목적 카테고리 — utils.goal_categories 에서 단일 소스로 관리 (design.md §4.1.1)
# PURPOSE_OPTIONS 는 legacy 드롭다운과의 호환을 위해 유지되었으나,
# Step 1.4 에서 GOAL_CATEGORIES 칩 UI 로 교체됨.


# ══════════════════════════════════════════════
# 인스타그램 미리보기/업로드 공통 컴포넌트 헬퍼
# ══════════════════════════════════════════════
# ══════════════════════════════════════════════
# 인스타그램 피드 미리보기/업로드 컴포넌트
# ══════════════════════════════════════════════
def render_instagram_preview_and_upload(product_name: str, image_bytes: bytes, caption_data, key_suffix: str, brand=None):
    st.markdown("---")
    st.markdown("### 📱 인스타그램 피드 미리보기")
    st.caption("실제로 인스타그램에 올라가면 폰에서 이렇게 보입니다.")

    col_preview, col_edit = st.columns([1, 1.2], gap="large")
    
    cap_key = f"cap_text_{key_suffix}"
    tag_key = f"cap_tags_{key_suffix}"
    
    current_caption = st.session_state.get(cap_key, caption_data.caption)
    current_tags = st.session_state.get(tag_key, caption_data.hashtags)

    with col_preview:
        with st.container(border=True):
            st.markdown(f"""
                <div class="ig-mock-header">
                    <div class="ig-avatar"></div>
                    <div>
                        <div class="ig-username">{product_name}_official</div>
                        <div class="ig-sponsored">Sponsored</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            st.image(image_bytes, width="stretch")
            
            html_caption = current_caption.replace('\n', '<br>')
            st.markdown(f"""
                <div style="padding-top:10px;">
                    <span style="font-size:22px;">❤️ 💬 ↗️</span><br>
                    <strong style="font-size:14px;">좋아요 8,241개</strong>
                </div>
                <div style='font-size: 14px; margin-top:8px;'>
                    <strong>{product_name}_official</strong> {html_caption}<br><br>
                    <span style='color:#00376b;'>{current_tags}</span>
                </div>
            """, unsafe_allow_html=True)

    with col_edit:
        with st.container(border=True):
            st.markdown("#### ✍️ 내 맘대로 글 수정하기")
            st.caption("오른쪽에 적힌 내용을 고치면 왼쪽 화면이 똑같이 따라서 바뀝니다. 사장님 맘에 쏙 들게 고쳐보세요!")
            edited_caption = st.text_area("✍️ 게시물 내용 (글)", value=caption_data.caption, height=160, key=cap_key)
            edited_tags = st.text_area("🏷️ 검색용 태그 (#)", value=caption_data.hashtags, height=80, key=tag_key)
            
            st.info("💡 글 내용이 모두 맘에 든다면, 아래 버튼을 눌러 우리 가게 인스타그램에 바로 올려보세요!")
            if st.button("🚀 내 인스타그램에 바로 올리기", type="primary", width="stretch", key=f"upload_btn_{key_suffix}"):
                # OAuth 이식: 업로드 직전 DB 의 사용자 토큰을 settings 에 동적 주입.
                # OAuth 연결이 없으면 기존 .env 의 META_ACCESS_TOKEN fallback 사용.
                from services.instagram_auth_adapter import apply_user_token
                from services.instagram_service import InstagramService

                if not apply_user_token(settings, brand):
                    st.warning(
                        "⚠️ 인스타그램 연결이 필요합니다. "
                        "왼쪽 사이드바에서 계정을 먼저 연결해주세요."
                    )
                    st.stop()

                ig_svc = InstagramService(settings)
                
                progress_container = st.empty()
                status_bar_container = st.empty()
                
                try:
                    idx = 0.0
                    if settings.is_mock_image:
                        upload_gen = ig_svc.upload_mock(image_bytes, f"{edited_caption}\n\n{edited_tags}")
                    else:
                        upload_gen = ig_svc.upload_real(image_bytes, f"{edited_caption}\n\n{edited_tags}")
                        
                    for status_msg in upload_gen:
                        if status_msg == "DONE":
                            progress_container.empty()
                            status_bar_container.empty()
                            # 게시 성공 시 generated_uploads 에 레코드 저장
                            _persist_generated_upload(
                                kind="feed",
                                caption=f"{edited_caption}\n\n{edited_tags}",
                                post_id=ig_svc.last_post_id,
                                posted_at=ig_svc.last_posted_at,
                            )
                            st.success(f"🎉 인스타그램 피드에 성공적으로 게시되었습니다!\n\n"
                                     f"- 올라간 계정: **@{product_name}_official**\n"
                                     f"- (안내: 현재는 연습용(MOCK) 모드입니다.)" if settings.is_mock_image else "")
                            st.balloons()
                        else:
                            idx += 0.2
                            progress_container.info(f"📡 {status_msg}")
                            status_bar_container.progress(min(idx, 1.0))  # S-2
                except Exception as e:
                    logger.exception("인스타 피드 업로드 실패")
                    st.error(f"❌ 업로드 중 문제가 발생했습니다 ({type(e).__name__}): {e}")
                    with st.expander("🔍 기술 상세 (디버깅)", expanded=False):
                        st.exception(e)

# ══════════════════════════════════════════════
# 인스타그램 스토리 미리보기/업로드 컴포넌트
# ══════════════════════════════════════════════
def render_instagram_story_preview_and_upload(product_name: str, image_bytes: bytes, story_copies: list[str], key_suffix: str, brand=None):
    st.markdown("---")
    st.markdown("### 📱 인스타그램 스토리 미리보기")
    st.caption("9:16 세로형 포맷으로, 블러 배경과 함께 세련되게 합성된 스토리 화면입니다.")

    col_preview, col_edit = st.columns([1, 1.2], gap="large")
    
    story_copy_key = f"story_copy_sel_{key_suffix}"
    
    with col_edit:
        with st.container(border=True):
            st.markdown("#### 📱 스토리 문구 선택하기")
            st.caption("이미지에 얹을 짧고 강렬한 문구를 골라보세요. 레퍼런스 스타일의 여백미를 살려 배치됩니다.")
            
            selected_copy = st.radio(
                "✍️ 마음에 드는 문구를 골라주세요",
                story_copies,
                key=story_copy_key
            )
            
            if st.button("✨ 선택한 문구로 스토리 이미지 만들기", width="stretch"):
                from services.image_service import ImageService
                img_svc = ImageService(settings)
                with st.spinner("9:16 포맷으로 예쁘게 합성 중입니다..."):
                    try:
                        composed_story = img_svc.compose_story_image(image_bytes, selected_copy)
                        st.session_state.story_result = composed_story
                        st.session_state.story_text = selected_copy
                    except Exception as e:
                        st.error(f"합성 중 오류 발생: {e}")

    with col_preview:
        if st.session_state.story_result:
            with st.container(border=True):
                # 인스타그램 스토리 목업 헤더
                st.markdown(f"""
                    <div style="display:flex; align-items:center; margin-bottom:10px;">
                        <div style="width:32px; height:32px; border-radius:50%; background:#eee; margin-right:8px; border: 2px solid #f09433;"></div>
                        <strong style="font-size:13px;">{product_name}</strong>
                        <span style="font-size:11px; color:#999; margin-left:5px;">12시간 전</span>
                    </div>
                """, unsafe_allow_html=True)
                
                st.image(st.session_state.story_result, width="stretch")
                st.caption("💡 실제 배경 블러 효과와 텍스트 레이아웃이 적용된 결과입니다.")
        else:
            st.info("왼쪽(혹은 위)에서 문구를 선택하고 버튼을 누르면 미리보기가 생성됩니다.")

    if st.session_state.story_result:
        st.write("")
        if st.button("🚀 위 스토리 바로 올리기", type="primary", width="stretch", key=f"story_upload_btn_{key_suffix}"):
            # OAuth 이식: 업로드 직전 DB 토큰 주입 가드 (피드 경로와 동일).
            from services.instagram_auth_adapter import apply_user_token
            from services.instagram_service import InstagramService

            if not apply_user_token(settings, brand):
                st.warning(
                    "⚠️ 인스타그램 연결이 필요합니다. "
                    "왼쪽 사이드바에서 계정을 먼저 연결해주세요."
                )
                st.stop()

            ig_svc = InstagramService(settings)
            
            progress_container = st.empty()
            status_bar_container = st.empty()
            
            try:
                idx = 0.0
                if settings.is_mock_image:
                    upload_gen = ig_svc.upload_mock(st.session_state.story_result, "", is_story=True)
                else:
                    upload_gen = ig_svc.upload_story(st.session_state.story_result)
                    
                for status_msg in upload_gen:
                    if status_msg == "DONE":
                        progress_container.empty()
                        status_bar_container.empty()
                        st.success("🎉 인스타그램 스토리에 성공적으로 게시되었습니다!")
                        st.balloons()
                    else:
                        idx += 0.25
                        progress_container.info(f"📡 {status_msg}")
                        status_bar_container.progress(min(idx, 1.0))  # S-2
            except Exception as e:
                logger.exception("인스타 스토리 업로드 실패")
                st.error(f"❌ 스토리 업로드 중 오류 발생 ({type(e).__name__}): {e}")
                with st.expander("🔍 기술 상세 (디버깅)", expanded=False):
                    st.exception(e)

# ══════════════════════════════════════════════
# 공통 헬퍼 — 업무 실행 함수
# ══════════════════════════════════════════════
def _stash_generated_image(image_bytes: bytes) -> None:
    """생성된 이미지 바이트를 staging 에 저장하고 경로를 session_state 에 보존.

    Step 2.4 — 이후 인스타 게시 성공 시 generated_upload.image_path 로 사용.
    """
    if not image_bytes:
        return
    path = save_to_staging(image_bytes, extension=".png")
    st.session_state.current_generated_image_path = str(path)


def _persist_generated_upload(
    *,
    kind: str,  # "feed" or "story"
    caption: str,
    post_id: str | None,
    posted_at,
) -> None:
    """인스타 게시 성공 시 generated_uploads 레코드 추가.

    docs/schema.md §3.6 — generation_output_id 기반.
    session_state.current_generation_output_id 는 2c-2-ii 의 생성 플로우가 저장한다.
    """
    from uuid import UUID

    output_id_str = st.session_state.get("current_generation_output_id")
    if not output_id_str:
        # 이 시점엔 Generation 저장이 선행되어 image output 이 있어야 정상.
        # 없다는 건 텍스트 전용 생성이었거나 저장이 실패했다는 뜻 — 업로드 차단.
        raise RuntimeError(
            "current_generation_output_id 가 없습니다. "
            "이미지 생성부터 먼저 수행해야 인스타 게시가 가능합니다."
        )

    output_uuid = UUID(output_id_str)

    async def _save():
        async with AsyncSessionLocal() as session:
            upload_service = UploadService(session)
            upload = await upload_service.create(
                generation_output_id=output_uuid,
                kind=kind,
                caption=caption,
            )
            if post_id is not None and posted_at is not None:
                await upload_service.mark_posted(
                    upload_id=upload.id,
                    instagram_post_id=post_id,
                    posted_at=posted_at,
                )

    try:
        run_async(_save())
    except Exception:
        logger.exception(
            "generated_upload 저장 실패 (output_id=%s, kind=%s)", output_id_str, kind
        )
        raise


def _prepare_reference(source_output_id: str | None) -> tuple[str | None, str]:
    """참조 GenerationOutput 을 ReferenceImage 로 upsert 하고 (ref_id, composition_prompt) 반환.

    생성 버튼 직후 호출. 이미 분석된 참조라면 기존 레코드 재사용 → 0 딜레이.
    새 참조면 GPT Vision 구도 분석 → 3~8초 (생성 소요시간에 묻힘).

    실패 시 예외를 그대로 위로 전파 — 참조를 선택했는데 반영 안 된 채 생성이 진행되면
    거짓 UX 이기 때문. 호출자 (_run_*_generation) 의 상위 except 가 UI 에 표시.
    """
    if not source_output_id:
        return None, ""

    from uuid import UUID
    from services.reference_service import ReferenceAnalyzer, ReferenceImageService

    analyzer = ReferenceAnalyzer(settings)

    async def _upsert() -> tuple[str, str]:
        async with AsyncSessionLocal() as session:
            svc = ReferenceImageService(session)
            ref = await svc.upsert_by_source_output(
                source_output_id=UUID(source_output_id),
                analyzer=analyzer,
            )
            return str(ref.id), ref.composition_prompt

    try:
        return run_async(_upsert())
    except Exception:
        logger.exception("참조 이미지 구도 분석 실패 (source_output_id=%s)", source_output_id)
        raise


def _save_generation_record(
    *,
    text_result: dict | None,
    image_bytes: bytes | None,
) -> None:
    """_run_*_generation 끝에 호출. Generation + GenerationOutput N개 INSERT.

    - 이미지가 있으면 staging 에 저장한 경로를 content_path 로 사용
    - 텍스트는 ad_copies/promo_sentences/story_copies 를 각각 kind 로 분리
    - 이미지 output 의 id 를 session_state.current_generation_output_id 에 저장
      (이후 인스타 게시 성공 시 _persist_generated_upload 가 읽음)
    """
    req = st.session_state.get("last_request") or {}
    product_name = req.get("product_name") or ""
    product_description = req.get("description") or ""
    goal = req.get("goal") or ""
    # 톤/스타일 — 결합 생성은 text_tone, 텍스트 전용은 text_tone, 이미지 전용은 image_style
    tone = req.get("text_tone") or req.get("image_style") or "기본"
    is_new_product = st.session_state.get("is_new_product", False)

    brand = st.session_state.get("_current_brand")
    if brand is None:
        # 방어적 — 온보딩 후에만 호출되므로 이론상 항상 있어야 함
        return

    # 이미지 저장
    image_path: str | None = None
    if image_bytes:
        image_path = st.session_state.get("current_generated_image_path")

    # 상품 원본 이미지 경로 (신상품 모드에서 staging 된 것)
    product_image_path = st.session_state.get("current_product_image_path")

    outputs: list[OutputSpec] = []
    if image_path:
        outputs.append(OutputSpec(kind="image", content_path=image_path))
    if text_result:
        for c in text_result.get("ad_copies", []) or []:
            outputs.append(OutputSpec(kind="ad_copy", content_text=c))
        for c in text_result.get("promo_sentences", []) or []:
            outputs.append(OutputSpec(kind="promo_sentence", content_text=c))
        for c in text_result.get("story_copies", []) or []:
            outputs.append(OutputSpec(kind="story_copy", content_text=c))

    if not outputs:
        return

    # 참조 이미지 FK — _prepare_reference 가 session_state 에 이미 id 를 넣어둠 (MVP 단일 참조).
    from uuid import UUID as _UUID
    _ref_id_str = st.session_state.get("current_reference_image_id")
    reference_image_id = _UUID(_ref_id_str) if _ref_id_str else None

    async def _save() -> None:
        async with AsyncSessionLocal() as session:
            svc = GenerationService(session)
            gen = await svc.create_with_outputs(
                brand_id=brand.id,
                reference_image_id=reference_image_id,
                product_name=product_name,
                product_description=product_description,
                product_image_path=product_image_path,
                goal=goal,
                tone=tone,
                is_new_product=is_new_product,
                outputs=outputs,
                langfuse_trace_id=st.session_state.get("_pending_langfuse_trace_id"),
            )
            # 이미지 output 의 id 를 session_state 에 보관 (업로드 시 FK 로 사용)
            # 텍스트 전용 생성이면 image output 이 없으므로 이전 값이 남아서 엉뚱한
            # 이미지가 업로드되지 않도록 명시적으로 None 리셋.
            image_output_id: str | None = None
            for o in gen.outputs:
                if o.kind == "image":
                    image_output_id = str(o.id)
                    break
            st.session_state.current_generation_output_id = image_output_id
            st.session_state.current_generation_id = str(gen.id)

    try:
        run_async(_save())
    except Exception:
        # 저장 실패 시 이전 값이 남아 엉뚱한 업로드가 뒤따르지 않게 세션 키를 파괴.
        st.session_state.current_generation_output_id = None
        st.session_state.current_generation_id = None
        logger.exception("Generation 저장 실패")
        raise


def _langfuse_trace_span(name: str):
    """Langfuse 루트 span 컨텍스트 매니저.

    - Langfuse 가 비활성(키 미설정 / import 실패) 인 경우 nullcontext 로 폴백.
    - span 안에서 langfuse.openai 로 래핑된 OpenAI 호출은 자동으로 같은 trace 에 귀속.
    - 블록 안에서 get_current_trace_id() 를 호출해 trace_id 를 꺼내 session_state 에 캐시.
    """
    import contextlib
    import logging

    try:
        from langfuse import get_client
        client = get_client()
        # no-op 클라이언트(키 미설정)면 start_as_current_observation 이 동작해도
        # trace 는 생성되지 않음. 그래도 컨텍스트는 OK.
        return client.start_as_current_observation(name=name, as_type="span")
    except Exception as e:  # noqa: BLE001
        logging.getLogger(__name__).warning("Langfuse span 시작 실패 → 추적 없이 진행: %s", e)
        return contextlib.nullcontext()


def _capture_langfuse_trace_id() -> None:
    """현재 활성 span 의 trace_id 를 session_state 에 보관.

    _save_generation_record 가 읽어 Generation.langfuse_trace_id 로 저장.
    """
    try:
        from langfuse import get_client
        tid = get_client().get_current_trace_id()
        st.session_state._pending_langfuse_trace_id = tid
    except Exception:  # noqa: BLE001
        st.session_state._pending_langfuse_trace_id = None


def _run_text_generation(name: str, desc: str, goal: str, tone_val: str, ui_tone_name: str, image_data: bytes = None) -> None:
    st.session_state.error_message = None
    st.session_state.error_exception = None
    st.session_state.last_request = {
        "product_name": name, "description": desc, "goal": goal, "text_tone": tone_val, "ui_text_tone": ui_tone_name,
        "image_data": image_data, "type": "홍보 글"
    }
    try:
        with _langfuse_trace_span("generation.text_only"):
            with st.spinner("💬 사장님을 대신해 멋진 홍보 글을 작성하고 있어요. 잠시만 기다려주세요..."):
                request = TextGenerationRequest(
                    product_name=name,
                    description=desc,
                    style=tone_val,
                    goal=goal,
                    image_data=image_data,
                    brand_prompt=st.session_state.get("brand_prompt", ""),
                    is_new_product=st.session_state.get("is_new_product", False),
                    reference_analysis="",  # 텍스트 단독 생성은 구도 주입 없음
                )
                response = text_service.generate_ad_copy(request)
            _capture_langfuse_trace_id()
        st.session_state.text_result = response.model_dump()
        # Generation + 텍스트 outputs 저장 (이미지 없음)
        _save_generation_record(text_result=response.model_dump(), image_bytes=None)
    except Exception as e:
        logger.exception("생성 플로우 실패")
        st.session_state.error_message = (
            f"❌ 문제가 발생했습니다. 다시 시도해주세요.\n"
            f"(타입: {type(e).__name__} / 상세: {e})"
        )
        st.session_state.error_exception = e

def _run_image_generation(name: str, desc: str, goal: str, style_val: str, ui_style_name: str, image_data: bytes = None, reference_image_paths: list[str] | None = None) -> None:
    st.session_state.error_message = None
    st.session_state.error_exception = None
    st.session_state.last_request = {
        "product_name": name, "description": desc, "goal": goal, "image_style": style_val, "ui_image_style": ui_style_name,
        "image_data": image_data, "reference_image_paths": reference_image_paths or [], "type": "홍보 사진"
    }
    try:
        # 참조 이미지 구도 분석 (선택 시에만, 재사용 있으면 캐시 히트 → 즉시).
        # 이 호출은 생성 trace 바깥에서 실행 — 별도 trace 로 남아도 됨.
        ref_id, composition_prompt = _prepare_reference(
            st.session_state.get("current_reference_source_output_id")
        )
        st.session_state.current_reference_image_id = ref_id

        with _langfuse_trace_span("generation.image_only"):
            with st.spinner("🖼️ 상품과 어울리는 예쁜 사진을 그리고 있어요... (약 10~20초 정도 걸립니다)"):
                request = ImageGenerationRequest(
                    product_name=name,
                    description=desc,
                    goal=goal,
                    style=style_val,
                    image_data=image_data,
                    reference_image_paths=reference_image_paths or [],
                    brand_prompt=st.session_state.get("brand_prompt", ""),
                    is_new_product=st.session_state.get("is_new_product", False),
                    reference_analysis=composition_prompt,
                )
                response = image_service.generate_ad_image(request)
            _capture_langfuse_trace_id()

        _stash_generated_image(response.image_data)
        st.session_state.image_result = response.model_dump()
        # Generation + image output 저장
        _save_generation_record(text_result=None, image_bytes=response.image_data)
    except Exception as e:
        logger.exception("생성 플로우 실패")
        st.session_state.error_message = (
            f"❌ 문제가 발생했습니다. 다시 시도해주세요.\n"
            f"(타입: {type(e).__name__} / 상세: {e})"
        )
        st.session_state.error_exception = e

def _run_combined_generation(name: str, desc: str, goal: str, tone_val: str, style_val: str, ui_tone_name: str, ui_style_name: str, image_data: bytes = None, reference_image_paths: list[str] | None = None) -> None:
    st.session_state.error_message = None
    st.session_state.error_exception = None
    st.session_state.last_request = {
        "product_name": name, "description": desc, "goal": goal, "text_tone": tone_val, "image_style": style_val,
        "ui_text_tone": ui_tone_name, "ui_image_style": ui_style_name, "image_data": image_data,
        "reference_image_paths": reference_image_paths or [], "type": "글과 사진 세트"
    }

    res_t, res_i = None, None
    brand = st.session_state.get("brand_prompt", "")
    is_new = st.session_state.get("is_new_product", False)
    try:
        # 참조 이미지 구도 분석 (선택 시에만). 분석 결과는 이미지 프롬프트에만 주입,
        # 텍스트 생성에는 영향 없음 (brand 톤과 섞이면 안 됨).
        ref_id, composition_prompt = _prepare_reference(
            st.session_state.get("current_reference_source_output_id")
        )
        st.session_state.current_reference_image_id = ref_id

        with _langfuse_trace_span("generation.combined"):
            with st.spinner("💬 [1단계] 사장님을 대신해 멋진 홍보 글을 먼저 작성하고 있어요..."):
                req_t = TextGenerationRequest(
                    product_name=name,
                    description=desc,
                    style=tone_val,
                    goal=goal,
                    image_data=image_data,
                    brand_prompt=brand,
                    is_new_product=is_new,
                    reference_analysis="",  # 텍스트에는 구도 주입 안 함
                )
                res_t = text_service.generate_ad_copy(req_t)
                st.session_state.text_result = res_t.model_dump()

            with st.spinner("🖼️ [2단계] 작성된 글과 어울리는 예쁜 홍보 사진을 알아서 그리고 있어요... (약 10~20초)"):
                hint_copy = res_t.ad_copies[0] if res_t.ad_copies else ""
                req_i = ImageGenerationRequest(
                    product_name=name,
                    description=desc,
                    goal=goal,
                    style=style_val,
                    prompt=hint_copy,
                    image_data=image_data,
                    reference_image_paths=reference_image_paths or [],
                    brand_prompt=brand,
                    is_new_product=is_new,
                    reference_analysis=composition_prompt,
                )
                res_i = image_service.generate_ad_image(req_i)
                _stash_generated_image(res_i.image_data)
                st.session_state.image_result = res_i.model_dump()
            _capture_langfuse_trace_id()
        # Generation + (image + 텍스트들) outputs 저장
        _save_generation_record(
            text_result=res_t.model_dump() if res_t else None,
            image_bytes=res_i.image_data if res_i else None,
        )
    except Exception as e:
        logger.exception("생성 플로우 실패")
        st.session_state.error_message = (
            f"❌ 문제가 발생했습니다. 다시 시도해주세요.\n"
            f"(타입: {type(e).__name__} / 상세: {e})"
        )
        st.session_state.error_exception = e

# ══════════════════════════════════════════════
# 헤더 / 탭 레이아웃
# ══════════════════════════════════════════════
st.markdown('<div class="title-gradient">✨ 사장님을 위한 AI 홍보 도우미</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">어려운 홍보 문구와 멋진 사진, 복잡한 설정 없이 알아서 만들어드려요!</div>', unsafe_allow_html=True)

with st.expander("🛠️ 시스템 환경 확인 (관리자용)", expanded=False):
    st.caption(f"이미지 백엔드: `{settings.IMAGE_BACKEND_KIND.value}`")
    if settings.is_mock_image:
        st.warning("🧪 현재 연습용 MOCK 모드입니다 (이미지/인스타 호출 없음).")
    elif not settings.is_api_ready:
        st.error("🔑 환경 설정이 올바르지 않습니다 (OPENAI_API_KEY 확인).")
    else:
        st.success("🟢 정상적으로 서비스와 연결되어 있습니다.")

st.write("")

tab_create, tab_archive = st.tabs(["✨ 새로 만들기", "🗂️ 예전에 만든 홍보물 보기"])

# ── 탭 1: 새로 만들기 ──
with tab_create:
    # 1. 상품 정보 섹션 (Phase 2 Step 2.3 — 신상품 토글 + 기존 상품 드롭다운)
    with st.container(border=True):
        st.markdown("#### <span class='step-badge'>1</span> 우리 가게 상품 정보 ✏️", unsafe_allow_html=True)

        is_new_product = st.toggle(
            "🆕 신상품으로 등록하기",
            value=st.session_state.get("is_new_product", False),
            key="is_new_product",
            help="체크하면 이 상품이 DB 에 새로 등록되어, 다음부터는 드롭다운에서 바로 선택할 수 있어요.",
        )

        # 기존 상품군 목록 조회 (드롭다운용) — product_name 으로 distinct
        async def _load_products():
            async with AsyncSessionLocal() as session:
                svc = GenerationService(session)
                return await svc.list_products(_loaded_brand.id)
        existing_products = run_async(_load_products())

        selected_product = None
        product_name = ""
        product_description = ""
        product_image = None  # UploadedFile 객체
        existing_raw_image_path: str | None = None  # 기존 상품의 raw 경로

        if is_new_product:
            # 신상품 입력 모드
            product_name = st.text_input(
                "📦 어떤 상품인가요? (필수)",
                value=st.session_state.product_name,
                placeholder="예: 무화과 크림치즈 휘낭시에",
                key="new_product_name_input",
            )
            product_description = st.text_input(
                "✒️ 상품 설명 (필수)",
                value=st.session_state.product_description,
                placeholder="예: 최고급 원재료, 유기농, 당일 한정 수량 등",
                key="new_product_desc_input",
            )
            product_image = st.file_uploader(
                "📸 상품 사진을 올려주세요 (필수)",
                type=["png", "jpg", "jpeg"],
                key="new_product_image_uploader",
            )
        else:
            # 기존 상품 드롭다운 모드
            if not existing_products:
                st.info(
                    "📭 아직 등록된 상품이 없어요. 위 토글을 켜서 신상품을 등록해주세요."
                )
            else:
                product_options = {
                    f"{p.product_name} — {p.product_description[:30]} · {p.generation_count}회 생성": p
                    for p in existing_products
                }
                selected_label = st.selectbox(
                    "📦 이번에 홍보할 상품을 골라주세요 (필수)",
                    options=list(product_options.keys()),
                    key="existing_product_selectbox",
                )
                selected_product = product_options.get(selected_label)
                if selected_product is not None:
                    product_name = selected_product.product_name
                    product_description = selected_product.product_description
                    existing_raw_image_path = selected_product.product_image_path

    # 2. 생성 타입 섹션
    with st.container(border=True):
        st.markdown("#### <span class='step-badge'>2</span> 무엇을 만드시겠어요? ⚙️", unsafe_allow_html=True)
        generation_type = st.radio(
            "선택해주세요:",
            ["홍보 글만 만들기", "홍보 이미지만 만들기", "글 + 이미지 함께 만들기"],
            index=2, # 기본값: 둘 다
            horizontal=True,
            label_visibility="collapsed"
        )

    # 3. 생성 옵션 섹션
    with st.container(border=True):
        st.markdown("#### <span class='step-badge'>3</span> 옵션 선택 🎨", unsafe_allow_html=True)

        # 광고 목적: 칩 6종 + 자유 텍스트 (design.md §4.1.1)
        st.markdown("🎯 이번 홍보의 목적은 무엇인가요?")
        goal_category = st.pills(
            label="광고 목적 카테고리",
            options=list(GOAL_CATEGORIES),
            default=GOAL_CATEGORIES[0],
            label_visibility="collapsed",
            key="goal_category_pills",
        )
        goal_freeform = st.text_input(
            "💬 자유 텍스트 (선택) — 카테고리 외의 세부 사항",
            placeholder="예: 여름 한정 · 배달의 민족 입점 기념",
            key="goal_freeform_input",
        )

        col_t, col_i = st.columns(2)

        selected_tone_ui = "기본 (가장 깔끔하게)"
        selected_style_ui = "기본 (가장 깔끔하게)"

        with col_t:
            if "글" in generation_type:
                selected_tone_ui = st.selectbox(
                    "✍️ 글은 어떤 느낌으로 만들어드릴까요? (톤)",
                    list(TONE_STYLE_DISPLAY_MAP.keys()),
                )

        with col_i:
            if "이미지" in generation_type or "사진" in generation_type:
                selected_style_ui = st.selectbox(
                    "🖼️ 이미지는 어떤 느낌으로 만들어드릴까요? (스타일)",
                    list(TONE_STYLE_DISPLAY_MAP.keys()),
                )

    # 4. 참조 이미지 갤러리 — 기존 게시물만 참조 가능 (docs/schema.md §3.2)
    with st.expander("🖼️ 이전 광고를 참고할까요? (선택)", expanded=False):
        selected_reference_paths, selected_reference_output_ids = render_reference_gallery()

    st.write("")
    
    # 생성 버튼: mock 모드면 무조건 활성, 아니면 OpenAI 키가 있어야 활성
    button_disabled = not settings.is_mock_image and not settings.is_api_ready
    if st.button("🚀 위 내용으로 똑똑하게 알아서 만들기", width="stretch", type="primary", disabled=button_disabled):
        # 0. 초기화
        st.session_state.text_result = None
        st.session_state.image_result = None
        st.session_state.caption_result = None
        st.session_state.error_message = None
    st.session_state.error_exception = None

        name = product_name.strip()

        # Phase 2 Step 2.3 — 토글 상태별 폼 검증
        if is_new_product:
            if not name:
                st.session_state.error_message = "⚠️ 신상품 이름을 입력해주세요!"
                st.rerun()
            if not product_description.strip():
                st.session_state.error_message = "⚠️ 신상품 설명을 입력해주세요!"
                st.rerun()
            if product_image is None:
                st.session_state.error_message = "⚠️ 신상품 사진을 업로드해주세요!"
                st.rerun()
        else:
            if selected_product is None:
                st.session_state.error_message = "⚠️ 기존 상품을 선택하거나 신상품 토글을 켜주세요!"
                st.rerun()

        # 1. 상태 업데이트
        st.session_state.product_name = name
        st.session_state.product_description = product_description.strip()
        st.session_state.generation_type = generation_type

        # 광고 목적 = 카테고리 + (선택) 자유 텍스트
        if goal_freeform.strip():
            final_ad_purpose = f"{goal_category} · {goal_freeform.strip()}"
        else:
            final_ad_purpose = goal_category
        st.session_state.ad_purpose = final_ad_purpose

        tone_val = TONE_STYLE_DISPLAY_MAP.get(selected_tone_ui, "기본")
        style_val = TONE_STYLE_DISPLAY_MAP.get(selected_style_ui, "기본")
        st.session_state.text_tone = tone_val
        st.session_state.image_style = style_val

        desc_payload = st.session_state.product_description

        # 신상품 모드: 업로드 이미지를 staging 에 저장 → product_image_path 로 기록
        if is_new_product:
            uploaded_bytes = product_image.getvalue()
            ext = Path(product_image.name).suffix.lower() or ".jpg"
            staged_path = save_to_staging(uploaded_bytes, extension=ext)
            st.session_state.current_product_image_path = str(staged_path)
            image_data = uploaded_bytes
        else:
            # 기존 상품 — 최근 Generation 의 product_image_path 에서 바이트 로드
            st.session_state.current_product_image_path = existing_raw_image_path
            if existing_raw_image_path and Path(existing_raw_image_path).exists():
                image_data = Path(existing_raw_image_path).read_bytes()
            else:
                image_data = None

        # 참조 이미지 — 첫 번째 선택만 Generation 에 FK 로 연결 (MVP 단일 참조)
        st.session_state.current_reference_source_output_id = (
            selected_reference_output_ids[0] if selected_reference_output_ids else None
        )

        # 2. 로직 분기 (이미지 생성 시 참조 이미지 갤러리 선택 결과도 전달)
        if generation_type == "글 + 이미지 함께 만들기":
            _run_combined_generation(
                name, desc_payload, final_ad_purpose, tone_val, style_val,
                selected_tone_ui, selected_style_ui, image_data,
                reference_image_paths=selected_reference_paths,
            )
        elif generation_type == "홍보 글만 만들기":
            _run_text_generation(name, desc_payload, final_ad_purpose, tone_val, selected_tone_ui, image_data)
        else:  # 이미지만
            _run_image_generation(
                name, desc_payload, final_ad_purpose, style_val,
                selected_style_ui, image_data,
                reference_image_paths=selected_reference_paths,
            )
            
        st.rerun()

    # 4. 결과 섹션 렌더링
    if st.session_state.error_message:
        st.error(st.session_state.error_message)
        # 디버깅용: 예외 객체가 있으면 traceback 까지 expander 로 노출
        exc = st.session_state.get("error_exception")
        if exc is not None:
            with st.expander("🔍 기술 상세 (디버깅)", expanded=False):
                st.exception(exc)

    if st.session_state.get("text_result") or st.session_state.get("image_result"):
        st.markdown("---")
        st.markdown("### 🎯 자동으로 완성된 우리 가게 홍보물")
        
        col_retry, col_down = st.columns([1, 1])
        with col_retry:
            if st.button("🔄 이 설정대로 다시 만들기 (재생성)", width="stretch"):
                req = st.session_state.last_request
                st.session_state.text_result = None
                st.session_state.image_result = None
                st.session_state.caption_result = None
                
                # H3 fix: 재생성 시에도 참조 이미지 갤러리 선택을 이어받는다.
                # last_request 에 저장된 값을 꺼내 _run_*_generation 에 전달.
                retry_refs = req.get("reference_image_paths") or []
                if req["type"] == "글과 사진 세트":
                    _run_combined_generation(
                        req["product_name"],
                        req["description"],
                        req.get("goal", "일반 홍보"),
                        req["text_tone"],
                        req["image_style"],
                        req["ui_text_tone"],
                        req["ui_image_style"],
                        req.get("image_data"),
                        reference_image_paths=retry_refs,
                    )
                elif req["type"] == "홍보 글":
                    _run_text_generation(
                        req["product_name"],
                        req["description"],
                        req.get("goal", "일반 홍보"),
                        req["text_tone"],
                        req["ui_text_tone"],
                        req.get("image_data"),
                    )
                else:
                    _run_image_generation(
                        req["product_name"],
                        req["description"],
                        req.get("goal", "일반 홍보"),
                        req["image_style"],
                        req["ui_image_style"],
                        req.get("image_data"),
                        reference_image_paths=retry_refs,
                    )
                st.rerun()
        
        st.write("")

    if st.session_state.get("text_result"):
        with st.container(border=True):
            result, request_info = st.session_state.text_result, st.session_state.last_request
            st.markdown(f"#### ✒️ 홍보 글 (선택하신 느낌: **{request_info.get('ui_text_tone', request_info.get('text_tone', '기본'))}**)")
            col_ad, col_promo = st.columns(2, gap="large")
            with col_ad:
                st.markdown("**💡 추천하는 짧은 홍보 문장**")
                for i, copy in enumerate(result.get("ad_copies", []), start=1):
                    st.caption(f"✨ 추천 {i}")
                    st.code(copy, language="plaintext")
            with col_promo:
                st.markdown("**📣 길게 쓸 수 있는 상세 설명**")
                for i, sentence in enumerate(result.get("promo_sentences", []), start=1):
                    st.caption(f"✔️ 문장 {i}")
                    st.code(sentence, language="plaintext")

    if st.session_state.get("image_result"):
        with st.container(border=True):
            result, request_info = st.session_state.image_result, st.session_state.last_request
            st.markdown(f"#### 📸 홍보 사진 (선택하신 느낌: **{request_info.get('ui_image_style', request_info.get('image_style', '기본'))}**)")
            col_img, col_info = st.columns([1, 1], gap="large")
            with col_img:
                st.image(result.get("image_data", b""), width="stretch", output_format="PNG")
            with col_info:
                st.markdown("**✔️ 고화질 홍보용 사진이 예쁘게 완성되었습니다.**")
                st.caption(f"- 사용된 상품명: `{request_info['product_name']}`")
                with st.expander("🛠️ (참고용) AI가 그림을 그릴 때 사용한 명령어 엿보기"):
                    st.code(result.get("revised_prompt"), language="text")
                st.success("사진에 오른쪽 클릭을 하거나, 아래 버튼을 눌러 저장할 수 있습니다.")
                st.download_button("💾 사진 기기에 다운로드 (저장)", data=result.get("image_data", b""), file_name=f"{request_info['product_name']}_홍보사진.png", mime="image/png", width="stretch")

    if st.session_state.get("text_result") and st.session_state.get("image_result"):
        req_info = st.session_state.last_request
        txt_res = st.session_state.text_result
        img_res = st.session_state.image_result

        with st.container(border=True):
            st.markdown("#### <span class='step-badge'>4</span> 인스타그램(SNS)에 바로 편하게 올리기", unsafe_allow_html=True)
            st.write("위에서 다 만들어진 글과 사진을 실제 인스타그램 피드나 스토리 포맷에 맞춰 보기 좋게 다듬어 가겠습니다.")
            
            col_feed_btn, col_story_btn = st.columns(2)
            
            with col_feed_btn:
                if st.button("📸 인스타 피드 게시물 만들기", width="stretch"):
                    from schemas.instagram_schema import CaptionGenerationRequest
                    from services.caption_service import CaptionService
                    with st.spinner("피드용 글과 태그를 정리하고 있어요..."):
                        try:
                            cap_svc = CaptionService(settings)
                            req = CaptionGenerationRequest(
                                product_name=req_info["product_name"],
                                description=req_info.get("description", ""),
                                ad_copies=txt_res.get("ad_copies", []),
                                style=req_info.get("text_tone", "기본"),
                                brand_prompt=st.session_state.get("brand_prompt", ""),
                                is_new_product=st.session_state.get("is_new_product", False),
                                reference_analysis="",  # 캡션엔 구도 주입 금지 (정책)
                            )
                            st.session_state.caption_result = cap_svc.generate_caption(req)
                            st.session_state.show_story_ui = False
                        except Exception as e:
                            st.error(f"❌ 피드 생성 중 오류: {e}")

            with col_story_btn:
                if st.button("📱 인스타 스토리 만들기", width="stretch"):
                    # 스토리는 별도의 LLM 호출 없이 기존 text_result의 story_copies를 활용함
                    st.session_state.show_story_ui = True
                    st.session_state.caption_result = None # 피드 UI 닫기

        if st.session_state.caption_result:
            render_instagram_preview_and_upload(
                product_name=req_info["product_name"],
                image_bytes=img_res.get("image_data"),
                caption_data=st.session_state.caption_result,
                key_suffix="new_create",
                brand=_loaded_brand,
            )

        if st.session_state.get("show_story_ui"):
            if "story_copies" in txt_res:
                render_instagram_story_preview_and_upload(
                    product_name=req_info["product_name"],
                    image_bytes=img_res.get("image_data"),
                    story_copies=txt_res["story_copies"],
                    key_suffix="new_create",
                    brand=_loaded_brand,
                )
            else:
                st.warning("⚠️ 이번 생성 결과에는 스토리용 카피가 포함되어 있지 않습니다. 다시 생성을 시도해주세요.")


# ── 탭 2: 히스토리 아카이브 ──
with tab_archive:
    st.markdown("### 🗂️ 예전에 만든 홍보물 보관함")
    st.caption("지금까지 사장님이 만드셨던 모든 홍보 글과 사진들이 날아가지 않고 이곳에 안전하게 보관되어 있습니다.")

    # 아카이브: 인스타에 실제로 게시된 업로드 목록 (GeneratedUpload + GenerationOutput 조인)
    async def _fetch_published():
        async with AsyncSessionLocal() as session:
            pairs = await UploadService(session).list_published(brand_id=_loaded_brand.id)
            # Generation 도 같이 필요 (product_name / goal 표시용)
            from services.generation_service import GenerationService as _GS
            svc = _GS(session)
            result = []
            for upload, output in pairs:
                gen = await svc.get_with_outputs(output.generation_id)
                if gen is not None:
                    result.append((upload, output, gen))
            return result

    items = run_async(_fetch_published())

    if not items:
        st.info(
            "아직 인스타그램에 올린 홍보물이 없습니다. "
            "'✨ 새로 만들기' 탭에서 우리 가게의 첫 번째 게시물을 만들어보세요!"
        )
    else:
        for upload, output, gen in items:
            posted_str = ""
            if upload.posted_at is not None:
                posted_str = upload.posted_at.strftime("%Y년 %m월 %d일 %H:%M")

            title = (
                f"📸 {gen.product_name} — {gen.goal} ({upload.kind})"
                + (f" · {posted_str}" if posted_str else "")
            )

            with st.expander(title):
                col_img, col_text = st.columns([1, 1.5])
                with col_img:
                    if output.content_path and Path(output.content_path).exists():
                        st.image(output.content_path, width="stretch")
                    else:
                        st.warning(f"❓ 이미지 파일 누락: {output.content_path}")
                with col_text:
                    st.markdown(f"**상품:** {gen.product_name}")
                    st.markdown(f"**광고 목적:** {gen.goal}")
                    st.markdown(f"**업로드 종류:** {upload.kind}")
                    st.markdown("**올라간 캡션**")
                    st.code(upload.caption, language="plaintext")
                    if upload.instagram_post_id:
                        st.caption(f"인스타 게시 ID: `{upload.instagram_post_id}`")
