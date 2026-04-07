"""생성형 AI 기반 광고 콘텐츠 제작 서비스 — 메인 엔트리포인트 (구조 리팩토링).

API 연동 및 데이터베이스(히스토리) 완성:
- SQLite & SQLAlchemy를 통한 비동기 생성 내역 저장/조회
- 멀티 탭 구조 (새로 만들기 / 아카이브) 지원

실행: streamlit run app.py
"""

import asyncio
import os

import streamlit as st

from config.database import init_db
from config.settings import get_settings, setup_logging
from ui.sidebar import render_sidebar_settings
from models.history import GenerationType
from schemas.history_schema import HistoryCreate
from schemas.image_schema import ImageGenerationRequest, ImageInferenceOptions
from schemas.text_schema import TextGenerationRequest
from services.history_service import HistoryService
from services.image_service import ImageService, ImageServiceError
from services.text_service import TextService, TextServiceError

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

@st.cache_resource
def setup_database() -> bool:
    asyncio.run(init_db())
    return True

setup_database()

def run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        return asyncio.run(coro)


def _build_current_inference_options() -> ImageInferenceOptions:
    """현재 사이드바 설정을 이미지 요청용 옵션으로 직렬화한다."""
    use_local_model = settings.USE_LOCAL_MODEL
    local_backend = settings.LOCAL_BACKEND if use_local_model else None

    return ImageInferenceOptions(
        use_local_model=use_local_model,
        image_model=settings.IMAGE_MODEL if not use_local_model else None,
        local_sd15_model_id=(
            settings.LOCAL_SD15_MODEL_ID if use_local_model else None
        ),
        local_backend=local_backend,
        local_inference_steps=(
            settings.LOCAL_INFERENCE_STEPS if use_local_model else None
        ),
        local_guidance_scale=(
            settings.LOCAL_GUIDANCE_SCALE if use_local_model else None
        ),
        local_ip_adapter_scale=(
            settings.LOCAL_IP_ADAPTER_SCALE
            if local_backend in {"ip_adapter", "hybrid"}
            else None
        ),
        local_img2img_strength=(
            settings.LOCAL_IMG2IMG_STRENGTH
            if local_backend in {"img2img", "hybrid"}
            else None
        ),
        local_ip_adapter_weight_name=(
            settings.LOCAL_IP_ADAPTER_WEIGHT_NAME
            if local_backend in {"ip_adapter", "hybrid"}
            else None
        ),
    )


def _coerce_inference_options(
    value: ImageInferenceOptions | dict | None,
) -> ImageInferenceOptions:
    """재생성 시 session_state에 저장된 dict를 다시 모델로 복원한다."""
    if value is None:
        return _build_current_inference_options()
    if isinstance(value, ImageInferenceOptions):
        return value
    return ImageInferenceOptions.model_validate(value)

# ══════════════════════════════════════════════
# Session State 초기화 (명확한 분리)
# ══════════════════════════════════════════════
_DEFAULT_STATE: dict = {
    # 1. 입력부 세션 관리
    "product_name": "",
    "product_description": "",
    "brand_philosophy": "",
    "product_image": None,
    "uploaded_image_names": [],
    "is_new_product": False,
    "is_renewal_product": False,
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
# UI 매핑용 딕셔너리
# ══════════════════════════════════════════════
TONE_DISPLAY_MAP = {
    "기본 (가장 깔끔하게)": "기본",
    "감성 (따뜻하고 부드럽게)": "감성",
    "고급 (격식있고 우아하게)": "고급",
    "유머 (재밌고 센스있게)": "유머",
    "심플 (핵심만 간단하게)": "심플"
}
STYLE_DISPLAY_MAP = {
    "기본 (가장 깔끔하게)": "기본",
    "감성 (따뜻하고 부드럽게)": "감성",
    "고급 (격식있고 우아하게)": "고급",
    "유머 (재밌고 센스있게)": "유머",
    "심플 (핵심만 간단하게)": "심플"
}
PURPOSE_OPTIONS = [
    "신상품 홍보", "할인 행사", "매장 소개", "시즌 홍보", "기타 (직접 입력)"
]


def _format_product_status(is_new_product: bool, is_renewal_product: bool) -> str:
    """선택된 상품 상태를 사람이 읽기 쉬운 라벨로 변환."""
    if is_new_product:
        return "신상품"
    if is_renewal_product:
        return "리뉴얼 상품"
    return "기존 상품"


# ══════════════════════════════════════════════
# 인스타그램 미리보기/업로드 공통 컴포넌트 헬퍼
# ══════════════════════════════════════════════
# ══════════════════════════════════════════════
# 인스타그램 피드 미리보기/업로드 컴포넌트
# ══════════════════════════════════════════════
def render_instagram_preview_and_upload(product_name: str, image_bytes: bytes, caption_data, key_suffix: str):
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
                from services.instagram_service import InstagramService
                ig_svc = InstagramService(settings)
                
                progress_container = st.empty()
                status_bar_container = st.empty()
                
                try:
                    idx = 0.0
                    if settings.USE_MOCK:
                        upload_gen = ig_svc.upload_mock(image_bytes, f"{edited_caption}\n\n{edited_tags}")
                    else:
                        upload_gen = ig_svc.upload_real(image_bytes, f"{edited_caption}\n\n{edited_tags}")
                        
                    for status_msg in upload_gen:
                        if status_msg == "DONE":
                            progress_container.empty()
                            status_bar_container.empty()
                            st.success(f"🎉 인스타그램 피드에 성공적으로 게시되었습니다!\n\n"
                                     f"- 올라간 계정: **@{product_name}_official**\n"
                                     f"- (안내: 현재는 연습용(MOCK) 모드입니다.)" if settings.USE_MOCK else "")
                            st.balloons()
                        else:
                            idx += 0.2
                            progress_container.info(f"📡 {status_msg}")
                            status_bar_container.progress(idx)
                except Exception as e:
                    st.error(f"❌ 업로드 중 문제가 발생했습니다: {e}")

# ══════════════════════════════════════════════
# 인스타그램 스토리 미리보기/업로드 컴포넌트
# ══════════════════════════════════════════════
def render_instagram_story_preview_and_upload(product_name: str, image_bytes: bytes, story_copies: list[str], key_suffix: str):
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
            from services.instagram_service import InstagramService
            ig_svc = InstagramService(settings)
            
            progress_container = st.empty()
            status_bar_container = st.empty()
            
            try:
                idx = 0.0
                if settings.USE_MOCK:
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
                        status_bar_container.progress(idx)
            except Exception as e:
                st.error(f"❌ 스토리 업로드 중 오류 발생: {e}")

# ══════════════════════════════════════════════
# 공통 헬퍼 — 업무 실행 함수
# ══════════════════════════════════════════════
def _run_text_generation(
    name: str,
    desc: str,
    goal: str,
    tone_val: str,
    ui_tone_name: str,
    image_data: bytes = None,
    brand_philosophy: str = "",
    is_new_product: bool = False,
    is_renewal_product: bool = False,
    attachment_names: list[str] | None = None,
) -> None:
    st.session_state.error_message = None
    st.session_state.last_request = {
        "product_name": name,
        "description": desc,
        "goal": goal,
        "text_tone": tone_val,
        "ui_text_tone": ui_tone_name,
        "image_data": image_data,
        "brand_philosophy": brand_philosophy,
        "is_new_product": is_new_product,
        "is_renewal_product": is_renewal_product,
        "attachment_names": attachment_names or [],
        "attachment_count": len(attachment_names or []),
        "type": "홍보 글",
    }
    try:
        with st.spinner("💬 사장님을 대신해 멋진 홍보 글을 작성하고 있어요. 잠시만 기다려주세요..."):
            request = TextGenerationRequest(
                product_name=name,
                description=desc,
                brand_philosophy=brand_philosophy,
                style=tone_val,
                goal=goal,
                image_data=image_data,
                is_new_product=is_new_product,
                is_renewal_product=is_renewal_product,
                attachment_count=len(attachment_names or []),
            )
            response = text_service.generate_ad_copy(request)
            
            async def _save():
                create_data = HistoryCreate(generation_type=GenerationType.TEXT, product_name=name, description=desc, style=tone_val, result_data=response.model_dump())
                await HistoryService().save_history(create_data)
            run_async(_save())
        st.session_state.text_result = response.model_dump()
    except Exception as e:
        st.session_state.error_message = f"❌ 문제가 발생했습니다. 다시 시도해주세요. (상세: {e})"

def _run_image_generation(
    name: str,
    desc: str,
    goal: str,
    style_val: str,
    ui_style_name: str,
    image_data: bytes = None,
    brand_philosophy: str = "",
    is_new_product: bool = False,
    is_renewal_product: bool = False,
    attachment_names: list[str] | None = None,
    inference_options: ImageInferenceOptions | dict | None = None,
) -> None:
    inference_options_obj = _coerce_inference_options(inference_options)
    st.session_state.error_message = None
    st.session_state.last_request = {
        "product_name": name,
        "description": desc,
        "goal": goal,
        "image_style": style_val,
        "ui_image_style": ui_style_name,
        "image_data": image_data,
        "brand_philosophy": brand_philosophy,
        "is_new_product": is_new_product,
        "is_renewal_product": is_renewal_product,
        "attachment_names": attachment_names or [],
        "attachment_count": len(attachment_names or []),
        "type": "홍보 사진",
        "inference_options": inference_options_obj.model_dump(exclude_none=True),
    }
    try:
        with st.spinner("🖼️ 상품과 어울리는 예쁜 사진을 그리고 있어요... (약 10~20초 정도 걸립니다)"):
            request = ImageGenerationRequest(
                product_name=name,
                description=desc,
                brand_philosophy=brand_philosophy,
                goal=goal,
                style=style_val,
                image_data=image_data,
                is_new_product=is_new_product,
                is_renewal_product=is_renewal_product,
                attachment_count=len(attachment_names or []),
                inference_options=inference_options_obj,
            )
            response = image_service.generate_ad_image(request)

            async def _save():
                create_data = HistoryCreate(generation_type=GenerationType.IMAGE, product_name=name, description=desc, style=style_val, result_data=response.model_dump())
                await HistoryService().save_history(create_data)
            run_async(_save())
        st.session_state.image_result = response.model_dump()
    except Exception as e:
        st.session_state.error_message = f"❌ 문제가 발생했습니다. 다시 시도해주세요. (상세: {e})"

def _run_combined_generation(
    name: str,
    desc: str,
    goal: str,
    tone_val: str,
    style_val: str,
    ui_tone_name: str,
    ui_style_name: str,
    image_data: bytes = None,
    brand_philosophy: str = "",
    is_new_product: bool = False,
    is_renewal_product: bool = False,
    attachment_names: list[str] | None = None,
    inference_options: ImageInferenceOptions | dict | None = None,
) -> None:
    inference_options_obj = _coerce_inference_options(inference_options)
    st.session_state.error_message = None
    st.session_state.last_request = {
        "product_name": name,
        "description": desc,
        "goal": goal,
        "text_tone": tone_val,
        "image_style": style_val,
        "ui_text_tone": ui_tone_name,
        "ui_image_style": ui_style_name,
        "image_data": image_data,
        "brand_philosophy": brand_philosophy,
        "is_new_product": is_new_product,
        "is_renewal_product": is_renewal_product,
        "attachment_names": attachment_names or [],
        "attachment_count": len(attachment_names or []),
        "type": "글과 사진 세트",
        "inference_options": inference_options_obj.model_dump(exclude_none=True),
    }
    
    res_t, res_i = None, None
    try:
        with st.spinner("💬 [1단계] 사장님을 대신해 멋진 홍보 글을 먼저 작성하고 있어요..."):
            req_t = TextGenerationRequest(
                product_name=name,
                description=desc,
                brand_philosophy=brand_philosophy,
                style=tone_val,
                goal=goal,
                image_data=image_data,
                is_new_product=is_new_product,
                is_renewal_product=is_renewal_product,
                attachment_count=len(attachment_names or []),
            )
            res_t = text_service.generate_ad_copy(req_t)
            st.session_state.text_result = res_t.model_dump()
            
        with st.spinner("🖼️ [2단계] 작성된 글과 어울리는 예쁜 홍보 사진을 알아서 그리고 있어요... (약 10~20초)"):
            hint_copy = res_t.ad_copies[0] if res_t.ad_copies else ""
            req_i = ImageGenerationRequest(
                product_name=name,
                description=desc,
                brand_philosophy=brand_philosophy,
                goal=goal,
                style=style_val,
                prompt=hint_copy,
                image_data=image_data,
                is_new_product=is_new_product,
                is_renewal_product=is_renewal_product,
                attachment_count=len(attachment_names or []),
                inference_options=inference_options_obj,
            )
            res_i = image_service.generate_ad_image(req_i)
            st.session_state.image_result = res_i.model_dump()
            
        async def _save_combined():
            combined_dict = {**res_t.model_dump(), **res_i.model_dump()}
            create_data = HistoryCreate(generation_type=GenerationType.COMBINED, product_name=name, description=desc, style=f"글:{tone_val}/사진:{style_val}", result_data=combined_dict)
            await HistoryService().save_history(create_data)
        run_async(_save_combined())
    except Exception as e:
        st.session_state.error_message = f"❌ 문제가 발생했습니다. 다시 시도해주세요. (상세: {e})"

# ══════════════════════════════════════════════
# 헤더 / 탭 레이아웃
# ══════════════════════════════════════════════
st.markdown('<div class="title-gradient">✨ 사장님을 위한 AI 홍보 도우미</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">어려운 홍보 문구와 멋진 사진, 복잡한 설정 없이 알아서 만들어드려요!</div>', unsafe_allow_html=True)

with st.expander("🛠️ 시스템 환경 확인 (관리자용)", expanded=False):
    if settings.USE_MOCK: st.warning("🧪 현재 연습용 테스트 모드입니다.")
    elif not settings.is_api_ready: st.error("🔑 환경 설정이 올바르지 않습니다.")
    else: st.success("🟢 정상적으로 서비스와 연결되어 있습니다.")

st.write("")

tab_create, tab_archive = st.tabs(["✨ 새로 만들기", "🗂️ 예전에 만든 홍보물 보기"])

# ── 탭 1: 새로 만들기 ──
with tab_create:
    # 1. 상품 정보 섹션
    with st.container(border=True):
        st.markdown("#### <span class='step-badge'>1</span> 우리 가게 상품 정보 ✏️", unsafe_allow_html=True)
        product_name = st.text_input("📦 어떤 상품을 홍보할까요? (필수)", value=st.session_state.product_name, placeholder="예: 무화과 크림치즈 휘낭시에")
        product_description = st.text_input("✒️ 상품의 장점을 짤막하게 알려주세요 (선택)", value=st.session_state.product_description, placeholder="예: 최고급 원재료, 유기농, 당일 한정 수량 등")
        brand_philosophy = st.text_area(
            "🧭 브랜드 철학이나 핵심 가치 (선택)",
            value=st.session_state.brand_philosophy,
            height=100,
            placeholder="예: 정직한 재료, 느린 장인정신, 일상 속 작은 사치",
        )
        col_product_flag_1, col_product_flag_2 = st.columns(2)
        with col_product_flag_1:
            is_new_product = st.checkbox("신상품입니다", value=st.session_state.is_new_product)
        with col_product_flag_2:
            is_renewal_product = st.checkbox("리뉴얼 상품입니다", value=st.session_state.is_renewal_product)

        if is_new_product and is_renewal_product:
            st.warning("신상품과 리뉴얼 상품은 동시에 선택할 수 없습니다. 하나만 선택해주세요.")

        product_images = st.file_uploader(
            "📸 첨부 이미지 (여러 장 가능, 선택사항)",
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True,
            help="여러 장을 올릴 수 있습니다. 현재 생성 파이프라인은 첫 번째 이미지를 대표 이미지로 사용합니다.",
        )
        if product_images:
            st.caption(
                f"첨부된 이미지 {len(product_images)}장: "
                + ", ".join(uploaded_file.name for uploaded_file in product_images)
            )

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
        
        ad_purpose_ui = st.selectbox("🎯 이번 홍보의 목적은 무엇인가요?", PURPOSE_OPTIONS)
        ad_purpose_custom = ""
        if ad_purpose_ui == "기타 (직접 입력)":
            ad_purpose_custom = st.text_input("홍보 목적을 직접 적어주세요", placeholder="예: 배달의 민족 입점 기념")
            
        col_t, col_i = st.columns(2)
        
        selected_tone_ui = "기본 (가장 깔끔하게)"
        selected_style_ui = "기본 (가장 깔끔하게)"
        
        with col_t:
            if "글" in generation_type:
                selected_tone_ui = st.selectbox("✍️ 글은 어떤 느낌으로 만들어드릴까요? (톤)", list(TONE_DISPLAY_MAP.keys()))
                
        with col_i:
            if "이미지" in generation_type or "사진" in generation_type:
                selected_style_ui = st.selectbox("🖼️ 이미지는 어떤 느낌으로 만들어드릴까요? (스타일)", list(STYLE_DISPLAY_MAP.keys()))

    st.write("")
    
    # 생성 버튼
    button_disabled = not settings.USE_MOCK and not settings.is_api_ready
    if st.button("🚀 위 내용으로 똑똑하게 알아서 만들기", width="stretch", type="primary", disabled=button_disabled):
        # 0. 초기화
        st.session_state.text_result = None
        st.session_state.image_result = None
        st.session_state.caption_result = None
        st.session_state.error_message = None

        name = product_name.strip()
        if not name:
            st.session_state.error_message = "⚠️ 위에 상품 이름을 먼저 입력해주세요! (예: 맛있는 사과)"
            st.rerun()
        if is_new_product and is_renewal_product:
            st.session_state.error_message = "⚠️ 신상품과 리뉴얼 상품은 동시에 선택할 수 없습니다. 하나만 선택해주세요."
            st.rerun()

        # 1. 상태 업데이트
        st.session_state.product_name = name
        st.session_state.product_description = product_description.strip()
        st.session_state.brand_philosophy = brand_philosophy.strip()
        st.session_state.is_new_product = is_new_product
        st.session_state.is_renewal_product = is_renewal_product
        st.session_state.generation_type = generation_type
        
        final_ad_purpose = ad_purpose_custom if ad_purpose_ui == "기타 (직접 입력)" else ad_purpose_ui
        st.session_state.ad_purpose = final_ad_purpose

        tone_val = TONE_DISPLAY_MAP.get(selected_tone_ui, "기본")
        style_val = STYLE_DISPLAY_MAP.get(selected_style_ui, "기본")
        st.session_state.text_tone = tone_val
        st.session_state.image_style = style_val

        # 설명에 목적 추가 로직 제거 (request.goal로 별도 전달됨)
        desc_payload = st.session_state.product_description
        
        # 여러 장 업로드를 받되, 현재 생성 파이프라인에는 첫 번째 이미지만 대표로 전달
        attachment_names = [uploaded_file.name for uploaded_file in product_images] if product_images else []
        st.session_state.uploaded_image_names = attachment_names
        image_data = product_images[0].getvalue() if product_images else None
        inference_options = _build_current_inference_options()

        # 2. 로직 분기
        if generation_type == "글 + 이미지 함께 만들기":
            _run_combined_generation(
                name,
                desc_payload,
                final_ad_purpose,
                tone_val,
                style_val,
                selected_tone_ui,
                selected_style_ui,
                image_data,
                st.session_state.brand_philosophy,
                is_new_product,
                is_renewal_product,
                attachment_names,
                inference_options,
            )
        elif generation_type == "홍보 글만 만들기":
            _run_text_generation(
                name,
                desc_payload,
                final_ad_purpose,
                tone_val,
                selected_tone_ui,
                image_data,
                st.session_state.brand_philosophy,
                is_new_product,
                is_renewal_product,
                attachment_names,
            )
        else: # 이미지만
            _run_image_generation(
                name,
                desc_payload,
                final_ad_purpose,
                style_val,
                selected_style_ui,
                image_data,
                st.session_state.brand_philosophy,
                is_new_product,
                is_renewal_product,
                attachment_names,
                inference_options,
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
                        req.get("brand_philosophy", ""),
                        req.get("is_new_product", False),
                        req.get("is_renewal_product", False),
                        req.get("attachment_names"),
                        req.get("inference_options"),
                    )
                elif req["type"] == "홍보 글":
                    _run_text_generation(
                        req["product_name"],
                        req["description"],
                        req.get("goal", "일반 홍보"),
                        req["text_tone"],
                        req["ui_text_tone"],
                        req.get("image_data"),
                        req.get("brand_philosophy", ""),
                        req.get("is_new_product", False),
                        req.get("is_renewal_product", False),
                        req.get("attachment_names"),
                    )
                else:
                    _run_image_generation(
                        req["product_name"],
                        req["description"],
                        req.get("goal", "일반 홍보"),
                        req["image_style"],
                        req["ui_image_style"],
                        req.get("image_data"),
                        req.get("brand_philosophy", ""),
                        req.get("is_new_product", False),
                        req.get("is_renewal_product", False),
                        req.get("attachment_names"),
                        req.get("inference_options"),
                    )
                st.rerun()
        
        st.write("")

    if st.session_state.get("text_result"):
        with st.container(border=True):
            result, request_info = st.session_state.text_result, st.session_state.last_request
            st.markdown(f"#### ✒️ 홍보 글 (선택하신 느낌: **{request_info.get('ui_text_tone', request_info.get('text_tone', '기본'))}**)")
            st.caption(f"- 상품 상태: `{_format_product_status(request_info.get('is_new_product', False), request_info.get('is_renewal_product', False))}`")
            st.caption(f"- 첨부 이미지: `{request_info.get('attachment_count', 0)}장`")
            if request_info.get("brand_philosophy"):
                st.caption(f"- 브랜드 철학: `{request_info['brand_philosophy']}`")
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
                st.caption(f"- 상품 상태: `{_format_product_status(request_info.get('is_new_product', False), request_info.get('is_renewal_product', False))}`")
                st.caption(f"- 첨부 이미지: `{request_info.get('attachment_count', 0)}장`")
                if request_info.get("brand_philosophy"):
                    st.caption(f"- 브랜드 철학: `{request_info['brand_philosophy']}`")
                with st.expander("🛠️ (참고용) AI가 그림을 그릴 때 사용한 명령어 엿보기"):
                    st.code(result.get("revised_prompt"), language="text")
                st.success("사진에 오른쪽 클릭을 하거나, 아래 버튼을 눌러 저장할 수 있습니다.")
                st.download_button("💾 사진 기기에 다운로드 (저장)", data=result.get("image_data", b""), file_name=f"{request_info['product_name']}_홍보사진.png", mime="image/png", width="stretch")

    # ── 배경 교체 테스트 (일관성 검증용) ──
    with st.expander("🔬 배경 교체 테스트 (상품 일관성 검증용)", expanded=False):
        st.caption("상품 이미지를 직접 올리고 두 가지 방식을 나란히 비교합니다.")
        bg_upload = st.file_uploader("상품 이미지 업로드", type=["png", "jpg", "jpeg"], key="bg_swap_upload")
        bg_style = st.selectbox("배경 스타일", list(STYLE_DISPLAY_MAP.keys()), key="bg_swap_style")
        bg_hint = st.text_input("추가 배경 힌트 (영어, 선택)", placeholder="e.g. forest, city night, beach", key="bg_swap_hint")
        bg_product_name = st.text_input("상품명 (선택)", placeholder="예: 토리든 세럼", key="bg_swap_name")

        if bg_upload:
            original_image_data: bytes = bg_upload.getvalue()
            col_btn_a, col_btn_b = st.columns(2)
            with col_btn_a:
                run_a = st.button("🖼️ A. 프롬프트만으로 교체", key="bg_swap_btn_a", help="원본 이미지 + '배경만 바꿔라' 프롬프트")
            with col_btn_b:
                run_b = st.button("✂️ B. 누끼 + 배경 생성", key="bg_swap_btn_b", help="rembg 누끼 → HF 배경생성 → 합성")

            from services.background_swap_service import BackgroundSwapService, BackgroundSwapError
            svc = BackgroundSwapService(settings)
            swap_kwargs = dict(
                product_image_bytes=bytes(original_image_data),
                style=STYLE_DISPLAY_MAP.get(bg_style, "기본"),
                goal="일반 홍보",
                product_name=bg_product_name,
                extra_hint=bg_hint,
            )

            if run_a:
                with st.status("A. 프롬프트로 배경 교체 중...", expanded=True) as status_a:
                    try:
                        st.write("HF API 호출 중...")
                        st.session_state["bg_swap_a"] = svc.swap_prompt_only(**swap_kwargs)
                        status_a.update(label="A. 완료", state="complete")
                    except BackgroundSwapError as e:
                        status_a.update(label=f"A. 오류: {e}", state="error")
                        st.error(f"❌ A 방식 오류: {e}")

            if run_b:
                with st.status("B. 누끼 + 배경 생성 중...", expanded=True) as status_b:
                    try:
                        st.write("rembg 누끼 제거 중...")
                        st.session_state["bg_swap_b"] = svc.swap_rembg(**swap_kwargs)
                        status_b.update(label="B. 완료", state="complete")
                    except BackgroundSwapError as e:
                        status_b.update(label=f"B. 오류: {e}", state="error")
                        st.error(f"❌ B 방식 오류: {e}")

            if st.session_state.get("bg_swap_a") or st.session_state.get("bg_swap_b"):
                col_orig, col_a, col_b = st.columns(3)
                with col_orig:
                    st.caption("원본")
                    st.image(original_image_data, use_container_width=True)
                with col_a:
                    st.caption("A. 프롬프트만")
                    if st.session_state.get("bg_swap_a"):
                        st.image(st.session_state["bg_swap_a"], use_container_width=True)
                        st.download_button("💾 A 저장", data=st.session_state["bg_swap_a"], file_name="bg_swap_A.png", mime="image/png", key="dl_a")
                with col_b:
                    st.caption("B. 누끼+합성")
                    if st.session_state.get("bg_swap_b"):
                        st.image(st.session_state["bg_swap_b"], use_container_width=True)
                        st.download_button("💾 B 저장", data=st.session_state["bg_swap_b"], file_name="bg_swap_B.png", mime="image/png", key="dl_b")

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
                                ad_copies=txt_res.get("ad_copies", []),
                                style=req_info["text_tone"],
                                brand_philosophy=req_info.get("brand_philosophy", ""),
                                is_new_product=req_info.get("is_new_product", False),
                                is_renewal_product=req_info.get("is_renewal_product", False),
                                attachment_count=req_info.get("attachment_count", 0),
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
                key_suffix="new_create"
            )

        if st.session_state.get("show_story_ui"):
            if "story_copies" in txt_res:
                render_instagram_story_preview_and_upload(
                    product_name=req_info["product_name"],
                    image_bytes=img_res.get("image_data"),
                    story_copies=txt_res["story_copies"],
                    key_suffix="new_create"
                )
            else:
                st.warning("⚠️ 이번 생성 결과에는 스토리용 카피가 포함되어 있지 않습니다. 다시 생성을 시도해주세요.")


# ── 탭 2: 히스토리 아카이브 ──
with tab_archive:
    st.markdown("### 🗂️ 예전에 만든 홍보물 보관함")
    st.caption("지금까지 사장님이 만드셨던 모든 홍보 글과 사진들이 날아가지 않고 이곳에 안전하게 보관되어 있습니다.")

    async def _fetch_histories():
        return await HistoryService().get_all_histories()

    histories = run_async(_fetch_histories())

    if not histories:
        st.info("아직 보관된 홍보물이 없습니다. '✨ 새로 만들기' 탭에서 우리 가게의 첫 번째 홍보물을 멋지게 만들어보세요!")
    else:
        for history in histories:
            icon = "📝(글만)" if history.generation_type == GenerationType.TEXT else "🖼️(사진만)" if history.generation_type == GenerationType.IMAGE else "💎(글+사진 세트)"
            
            title = f"[{icon}] {history.product_name} ─ {history.style} ─ {history.created_at.strftime('%Y년 %m월 %d일 %H:%M')}"

            with st.expander(title):
                res_data = history.result_data

                if history.generation_type == GenerationType.TEXT:
                    st.markdown("**👉 추천하는 짧은 홍보 문장**")
                    for copy in res_data.get("ad_copies", []):
                        st.code(copy, language="plaintext")
                    if res_data.get("promo_sentences"):
                        st.markdown("**📣 길게 쓸 수 있는 상세 설명**")
                        for sentence in res_data.get("promo_sentences", []):
                            st.code(sentence, language="plaintext")
                elif history.generation_type == GenerationType.IMAGE:
                    img_path = res_data.get("image_path")
                    if img_path and os.path.exists(img_path): st.image(img_path)
                elif history.generation_type == GenerationType.COMBINED:
                    col_t, col_i = st.columns([1.5, 1])
                    with col_t:
                        st.markdown("**👉 추천하는 짧은 홍보 문장**")
                        for copy in res_data.get("ad_copies", []):
                            st.code(copy, language="plaintext")
                        if res_data.get("promo_sentences"):
                            st.markdown("**📣 길게 쓸 수 있는 상세 설명**")
                            for sentence in res_data.get("promo_sentences", []):
                                st.code(sentence, language="plaintext")
                    with col_i:
                        img_path = res_data.get("image_path")
                        if img_path and os.path.exists(img_path):
                            st.image(img_path, width="stretch")
                        
                    st.divider()
                    
                    if st.button(f"🪄 이 결과물을 사용해서 다시 인스타그램에 올리기", key=f"gen_cap_{history.id}", width="stretch"):
                        from schemas.instagram_schema import CaptionGenerationRequest
                        from services.caption_service import CaptionService
                        with st.spinner("선택하신 홍보물을 싹 모아서 인스타그램용 글 스타일로 새롭게 정리하고 있어요..."):
                            cap_svc = CaptionService(settings)
                            # 히스토리에 있는 건 원본 style (tone/style 복합 문자열일수도 있지만)
                            # caption_service는 style 파라미터를 그대로 사용하므로 전달
                            req = CaptionGenerationRequest(product_name=history.product_name, ad_copies=res_data.get("ad_copies", []), style="기본")
                            st.session_state.history_captions[str(history.id)] = cap_svc.generate_caption(req)
                    
                    cap_result = st.session_state.history_captions.get(str(history.id))
                    if cap_result:
                        with open(img_path, "rb") as f:
                            img_bytes = f.read()
                        
                        render_instagram_preview_and_upload(
                            product_name=history.product_name,
                            image_bytes=img_bytes,
                            caption_data=cap_result,
                            key_suffix=f"archive_{history.id}"
                        )
