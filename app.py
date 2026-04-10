"""생성형 AI 기반 광고 콘텐츠 제작 서비스 — 메인 엔트리포인트 (구조 리팩토링).

API 연동 및 데이터베이스(히스토리) 완성:
- SQLite & SQLAlchemy를 통한 비동기 생성 내역 저장/조회
- 멀티 탭 구조 (새로 만들기 / 아카이브) 지원

실행: streamlit run app.py
"""

import asyncio
import os
from pathlib import Path

import streamlit as st

from config.database import AsyncSessionLocal, init_db
from config.settings import get_settings, setup_logging
from ui.instagram_connect import render_instagram_connection
from ui.onboarding import render_onboarding_screen
from ui.reference_gallery import render_reference_gallery
from ui.sidebar import render_sidebar_settings
from schemas.image_schema import ImageGenerationRequest
from schemas.text_schema import TextGenerationRequest
from services.brand_image_service import BrandImageService
from services.image_service import ImageService, ImageServiceError
from services.product_service import ProductService
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
    "last_request": None,
    "history_captions": {},
}
for key, default in _DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ══════════════════════════════════════════════
# 온보딩 라우팅 + brand_image 본문 로드 (Phase 2 Step 2.1 + Step A)
# ══════════════════════════════════════════════
# brand_image 가 DB 에 없으면 온보딩 화면만 렌더하고 조기 return.
# 존재하면 본문(content) + 구조화 필드(brand_name, brand_color)를 읽어
# 하나의 brand_prompt 문자열로 합쳐 session_state 에 캐시한다.
# 이후 광고 생성 시 request.brand_prompt 로 주입된다 (design.md §2.3).
async def _load_brand():
    """온보딩된 BrandImage 객체를 통째 반환 (없으면 None).

    OAuth 이식: 이전에는 brand_prompt 문자열만 반환했지만, Instagram OAuth
    통합이 `brand_config.id` (== BrandImage.id: UUID) 를 필요로 하므로
    객체 자체를 돌려주고 호출부에서 prompt 와 id 를 각각 꺼내 쓴다.
    """
    async with AsyncSessionLocal() as session:
        service = BrandImageService(session)
        brand = await service.get_for_user("default")
        return brand


def _compose_brand_prompt(
    *, content: str, brand_name: str | None, brand_color: str | None
) -> str:
    """구조화 필드 (brand_name/brand_color) 를 content 앞에 프리픽스로 합친다.

    Song 이식 방안 B — 별도 파라미터 없이 brand_prompt 하나로 모두 전달.
    """
    prefix_lines: list[str] = []
    if brand_name:
        prefix_lines.append(f"브랜드 이름: {brand_name}")
    if brand_color:
        prefix_lines.append(f"브랜드 대표 색상: {brand_color}")
    if not prefix_lines:
        return content
    return "\n".join(prefix_lines) + "\n\n" + content


_loaded_brand = run_async(_load_brand())
if _loaded_brand is None:
    render_onboarding_screen(settings)
    st.stop()

# 이후 _run_*_generation 이 읽어쓸 수 있도록 session_state 에 저장
st.session_state.brand_prompt = _compose_brand_prompt(
    content=_loaded_brand.content,
    brand_name=_loaded_brand.brand_name,
    brand_color=_loaded_brand.brand_color,
)

# Instagram OAuth 이식: 사이드바 render 와 업로드 가드가 BrandImage 를
# `brand_config` 인자로 받는다 (duck typing — `.id: UUID` 만 필요).
# 옵션 1 결정: docs/instagram_oauth_won_integration_notes.md 참고.
_brand_image = _loaded_brand

# 사이드바 인스타 연결 UI — render_sidebar_settings(IMAGE_BACKEND_KIND enum)
# 블록 아래에 추가됨. onboarded 이후에만 렌더되므로 이 지점에서 호출한다.
# META_APP_ID / META_APP_SECRET 미설정 시 내부에서 조기 return → 기존 .env 경로만
# 쓰는 환경에선 완전 no-op.
render_instagram_connection(settings, brand_config=_brand_image)


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
def render_instagram_preview_and_upload(product_name: str, image_bytes: bytes, caption_data, key_suffix: str, brand_config=None):
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

                if not apply_user_token(settings, brand_config):
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
                            # Step 2.4 — 게시 성공 시 generated_upload 저장
                            _persist_generated_upload(
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
                    st.error(f"❌ 업로드 중 문제가 발생했습니다: {e}")

# ══════════════════════════════════════════════
# 인스타그램 스토리 미리보기/업로드 컴포넌트
# ══════════════════════════════════════════════
def render_instagram_story_preview_and_upload(product_name: str, image_bytes: bytes, story_copies: list[str], key_suffix: str, brand_config=None):
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

            if not apply_user_token(settings, brand_config):
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
                st.error(f"❌ 스토리 업로드 중 오류 발생: {e}")

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
    caption: str,
    post_id: str | None,
    posted_at,
) -> None:
    """인스타 게시 성공 시 generated_upload 테이블에 레코드 추가.

    Step 2.4 — 광고 생성/업로드 흐름을 통해 축적된 session_state 값(current_product_id,
    current_generated_image_path, ad_purpose 의 카테고리) 을 꺼내서 저장.
    """
    from uuid import UUID

    product_id_str = st.session_state.get("current_product_id")
    image_path = st.session_state.get("current_generated_image_path")
    if not product_id_str or not image_path:
        logger_msg = "generated_upload 저장 스킵 — product_id 또는 image_path 누락"
        import logging
        logging.getLogger(__name__).warning(logger_msg)
        return

    goal_text = st.session_state.get("ad_purpose", "")
    # "카테고리 · 자유텍스트" → 분리
    if " · " in goal_text:
        goal_category, goal_freeform = goal_text.split(" · ", 1)
    else:
        goal_category = goal_text
        goal_freeform = ""

    product_uuid = UUID(product_id_str)

    async def _save():
        async with AsyncSessionLocal() as session:
            upload_service = UploadService(session)
            upload = await upload_service.create(
                product_id=product_uuid,
                image_path=image_path,
                caption=caption,
                goal_category=goal_category,
                goal_freeform=goal_freeform,
            )
            if post_id is not None and posted_at is not None:
                await upload_service.mark_posted(
                    upload_id=upload.id,
                    instagram_post_id=post_id,
                    posted_at=posted_at,
                )

    run_async(_save())


def _run_text_generation(name: str, desc: str, goal: str, tone_val: str, ui_tone_name: str, image_data: bytes = None) -> None:
    st.session_state.error_message = None
    st.session_state.last_request = {
        "product_name": name, "description": desc, "goal": goal, "text_tone": tone_val, "ui_text_tone": ui_tone_name,
        "image_data": image_data, "type": "홍보 글"
    }
    try:
        with st.spinner("💬 사장님을 대신해 멋진 홍보 글을 작성하고 있어요. 잠시만 기다려주세요..."):
            request = TextGenerationRequest(
                product_name=name,
                description=desc,
                style=tone_val,
                goal=goal,
                image_data=image_data,
                brand_prompt=st.session_state.get("brand_prompt", ""),
                is_new_product=st.session_state.get("is_new_product", False),
                reference_analysis="",  # TODO: DB 에서 참조 이미지 분석 텍스트 가져오기
            )
            response = text_service.generate_ad_copy(request)
        # Step 2.5: legacy HistoryService 호출 제거.
        # 텍스트 전용 생성은 DB 에 기록되지 않는다. 이미지+인스타 게시 후 generated_upload 에만 저장.
        st.session_state.text_result = response.model_dump()
    except Exception as e:
        st.session_state.error_message = f"❌ 문제가 발생했습니다. 다시 시도해주세요. (상세: {e})"

def _run_image_generation(name: str, desc: str, goal: str, style_val: str, ui_style_name: str, image_data: bytes = None, reference_image_paths: list[str] | None = None) -> None:
    st.session_state.error_message = None
    st.session_state.last_request = {
        "product_name": name, "description": desc, "goal": goal, "image_style": style_val, "ui_image_style": ui_style_name,
        "image_data": image_data, "reference_image_paths": reference_image_paths or [], "type": "홍보 사진"
    }
    try:
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
                reference_analysis="",  # TODO: DB 에서 참조 이미지 분석 텍스트 가져오기
            )
            response = image_service.generate_ad_image(request)

        # Step 2.4 — 생성 결과를 staging 에 저장해 인스타 게시 후 generated_upload 에 경로 기록
        _stash_generated_image(response.image_data)
        st.session_state.image_result = response.model_dump()
    except Exception as e:
        st.session_state.error_message = f"❌ 문제가 발생했습니다. 다시 시도해주세요. (상세: {e})"

def _run_combined_generation(name: str, desc: str, goal: str, tone_val: str, style_val: str, ui_tone_name: str, ui_style_name: str, image_data: bytes = None, reference_image_paths: list[str] | None = None) -> None:
    st.session_state.error_message = None
    st.session_state.last_request = {
        "product_name": name, "description": desc, "goal": goal, "text_tone": tone_val, "image_style": style_val,
        "ui_text_tone": ui_tone_name, "ui_image_style": ui_style_name, "image_data": image_data,
        "reference_image_paths": reference_image_paths or [], "type": "글과 사진 세트"
    }

    res_t, res_i = None, None
    brand = st.session_state.get("brand_prompt", "")
    is_new = st.session_state.get("is_new_product", False)
    try:
        with st.spinner("💬 [1단계] 사장님을 대신해 멋진 홍보 글을 먼저 작성하고 있어요..."):
            req_t = TextGenerationRequest(
                product_name=name,
                description=desc,
                style=tone_val,
                goal=goal,
                image_data=image_data,
                brand_prompt=brand,
                is_new_product=is_new,
                reference_analysis="",  # TODO
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
                reference_analysis="",  # TODO
            )
            res_i = image_service.generate_ad_image(req_i)
            # Step 2.4 — 생성 결과를 staging 에 저장
            _stash_generated_image(res_i.image_data)
            st.session_state.image_result = res_i.model_dump()
        # Step 2.5: legacy HistoryService 호출 제거. 기록은 인스타 게시 후 generated_upload 에만.
    except Exception as e:
        st.session_state.error_message = f"❌ 문제가 발생했습니다. 다시 시도해주세요. (상세: {e})"

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

        # 기존 상품 목록 조회 (드롭다운 또는 안내용)
        async def _load_products():
            from services.product_service import ProductService
            async with AsyncSessionLocal() as session:
                return await ProductService(session).list_all()
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
                    f"{p.name} — {p.description[:30]}": p
                    for p in existing_products
                }
                selected_label = st.selectbox(
                    "📦 이번에 홍보할 상품을 골라주세요 (필수)",
                    options=list(product_options.keys()),
                    key="existing_product_selectbox",
                )
                selected_product = product_options.get(selected_label)
                if selected_product is not None:
                    product_name = selected_product.name
                    product_description = selected_product.description
                    existing_raw_image_path = selected_product.raw_image_path

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

    # 4. 참조 이미지 갤러리 (Phase 2 Step 2.2)
    with st.expander("🖼️ 이전 광고를 참고할까요? (선택)", expanded=False):
        selected_reference_paths: list[str] = render_reference_gallery()

    st.write("")
    
    # 생성 버튼: mock 모드면 무조건 활성, 아니면 OpenAI 키가 있어야 활성
    button_disabled = not settings.is_mock_image and not settings.is_api_ready
    if st.button("🚀 위 내용으로 똑똑하게 알아서 만들기", width="stretch", type="primary", disabled=button_disabled):
        # 0. 초기화
        st.session_state.text_result = None
        st.session_state.image_result = None
        st.session_state.caption_result = None
        st.session_state.error_message = None

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

        # Phase 2 Step 2.3 — raw 이미지 추출 + 신상품 등록
        if is_new_product:
            # (1) 업로드 파일 즉시 staging 저장 (design.md §4.4 하이브리드)
            uploaded_bytes = product_image.getvalue()
            ext = Path(product_image.name).suffix.lower() or ".jpg"
            staged_path = save_to_staging(uploaded_bytes, extension=ext)

            # (2) Product 테이블에 INSERT (동기 — MVP. 백그라운드화는 Step 2.5)
            async def _register_product():
                async with AsyncSessionLocal() as session:
                    return await ProductService(session).create(
                        name=name,
                        description=desc_payload,
                        raw_image_path=str(staged_path),
                    )
            new_product = run_async(_register_product())

            # Step 2.4 — 인스타 게시 시점에 쓸 수 있도록 session 에 product id 저장
            st.session_state.current_product_id = str(new_product.id)
            image_data = uploaded_bytes
        else:
            # 기존 상품 — DB 의 raw_image_path 에서 바이트 로드
            st.session_state.current_product_id = str(selected_product.id)
            if existing_raw_image_path and Path(existing_raw_image_path).exists():
                image_data = Path(existing_raw_image_path).read_bytes()
            else:
                image_data = None

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
                                reference_analysis="",  # TODO
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
                brand_config=_brand_image,
            )

        if st.session_state.get("show_story_ui"):
            if "story_copies" in txt_res:
                render_instagram_story_preview_and_upload(
                    product_name=req_info["product_name"],
                    image_bytes=img_res.get("image_data"),
                    story_copies=txt_res["story_copies"],
                    key_suffix="new_create",
                    brand_config=_brand_image,
                )
            else:
                st.warning("⚠️ 이번 생성 결과에는 스토리용 카피가 포함되어 있지 않습니다. 다시 생성을 시도해주세요.")


# ── 탭 2: 히스토리 아카이브 ──
with tab_archive:
    st.markdown("### 🗂️ 예전에 만든 홍보물 보관함")
    st.caption("지금까지 사장님이 만드셨던 모든 홍보 글과 사진들이 날아가지 않고 이곳에 안전하게 보관되어 있습니다.")

    # Step 2.5 — legacy HistoryService 제거. 아카이브는 이제 generated_upload 기반.
    # 인스타에 실제로 게시된 항목만 표시 (list_published).

    async def _fetch_uploads_and_products():
        """게시된 업로드와 관련 상품을 한 번에 조회."""
        async with AsyncSessionLocal() as session:
            uploads = await UploadService(session).list_published()
            products = await ProductService(session).list_all()
        products_by_id = {p.id: p for p in products}
        return uploads, products_by_id

    uploads, products_by_id = run_async(_fetch_uploads_and_products())

    if not uploads:
        st.info(
            "아직 인스타그램에 올린 홍보물이 없습니다. "
            "'✨ 새로 만들기' 탭에서 우리 가게의 첫 번째 게시물을 만들어보세요!"
        )
    else:
        for upload in uploads:
            product = products_by_id.get(upload.product_id)
            product_name = product.name if product else "알 수 없는 상품"

            posted_str = ""
            if upload.posted_at is not None:
                posted_str = upload.posted_at.strftime("%Y년 %m월 %d일 %H:%M")

            title = (
                f"📸 {product_name} — {upload.goal_category}"
                + (f" · {posted_str}" if posted_str else "")
            )

            with st.expander(title):
                col_img, col_text = st.columns([1, 1.5])
                with col_img:
                    if Path(upload.image_path).exists():
                        st.image(upload.image_path, width="stretch")
                    else:
                        st.warning(f"❓ 이미지 파일 누락: {upload.image_path}")
                with col_text:
                    st.markdown(f"**상품:** {product_name}")
                    st.markdown(f"**광고 목적:** {upload.goal_category}")
                    if upload.goal_freeform:
                        st.markdown(f"**자유 텍스트:** {upload.goal_freeform}")
                    st.markdown("**올라간 캡션**")
                    st.code(upload.caption, language="plaintext")
                    if upload.instagram_post_id:
                        st.caption(f"인스타 게시 ID: `{upload.instagram_post_id}`")
