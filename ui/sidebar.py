"""사이드바 UI — 로컬 모델 실험 설정.

app.py에서 `from ui.sidebar import render_sidebar_settings`로 import 후
`render_sidebar_settings(settings)` 한 줄로 호출합니다.
"""

import streamlit as st

# 백엔드별 추천 기본값
# IP-Adapter: CLIP 임베딩으로 스타일 주입. scale 높여야 참조 반영 강해짐.
#             guidance 낮추면 텍스트 구속이 줄어 이미지 표현이 자유로워짐.
# img2img:    참조 이미지 직접 노이즈화 후 재생성. strength 낮을수록 원본 충실.
#             guidance 높이면 프롬프트 방향으로 더 많이 바뀜.
# hybrid:     img2img 베이스 위에 IP-Adapter 스타일 추가.
#             strength 낮게 + ip_scale 중간으로 시작 권장.
_BACKEND_DEFAULTS = {
    "ip_adapter": {"steps": 18, "guidance": 5.0, "ip_scale": 0.9, "strength": None},
    "img2img":    {"steps": 20, "guidance": 8.0, "ip_scale": None, "strength": 0.4},
    "hybrid":     {"steps": 20, "guidance": 7.0, "ip_scale": 0.6, "strength": 0.45},
}

_BACKEND_TIPS = {
    "ip_adapter": "💡 scale 0.8+ 권장 — 낮으면 참조 반영 약함",
    "img2img":    "💡 strength 0.3~0.5 권장 — 낮을수록 원본 보존",
    "hybrid":     "💡 strength 낮게 + ip_scale 중간으로 시작",
}

_WEIGHT_OPTIONS = {
    "ip-adapter_sd15.bin (기본)": "ip-adapter_sd15.bin",
    "ip-adapter-plus_sd15.bin (디테일↑)": "ip-adapter-plus_sd15.bin",
}

_HF_MODEL_OPTIONS = {
    "FLUX.1-schnell (고품질)": "black-forest-labs/FLUX.1-schnell",
    "SDXL Base 1.0 (안정적)": "stabilityai/stable-diffusion-xl-base-1.0",
}


def render_sidebar_settings(settings) -> None:
    """사이드바에 로컬 모델 설정 UI를 렌더링하고 settings 객체를 직접 수정."""
    with st.sidebar:
        st.markdown("## ⚙️ 이미지 생성 설정")
        st.caption("로컬 모델(SD 1.5) 실험용 설정입니다.")

        use_local = st.toggle(
            "로컬 모델 사용",
            value=settings.USE_LOCAL_MODEL,
            help="ON: 로컬 diffusers 모델 / OFF: Hugging Face API",
        )
        settings.USE_LOCAL_MODEL = use_local

        if use_local:
            st.markdown("#### 베이스 모델")
            settings.LOCAL_SD15_MODEL_ID = st.text_input(
                "로컬 Stable Diffusion 모델 ID",
                value=settings.LOCAL_SD15_MODEL_ID,
                help="고급 옵션입니다. 기본값은 runwayml/stable-diffusion-v1-5 입니다.",
            )

            st.markdown("#### 백엔드 선택")
            backend_labels = {
                "IP-Adapter (스타일 주입)": "ip_adapter",
                "img2img (구조 보존)":      "img2img",
                "Hybrid (구조 + 스타일)":   "hybrid",
            }
            current_backend = getattr(settings, "LOCAL_BACKEND", "ip_adapter")
            selected_label = st.radio(
                "백엔드",
                list(backend_labels.keys()),
                index=list(backend_labels.values()).index(current_backend),
                label_visibility="collapsed",
            )
            backend = backend_labels[selected_label]
            settings.LOCAL_BACKEND = backend
            d = _BACKEND_DEFAULTS[backend]

            st.markdown("#### 파라미터")
            st.caption(_BACKEND_TIPS[backend])

            settings.LOCAL_INFERENCE_STEPS = st.slider(
                "추론 스텝 수", 10, 50, value=d["steps"],
                help="많을수록 품질↑ 속도↓",
            )
            settings.LOCAL_GUIDANCE_SCALE = st.slider(
                "Guidance Scale", 1.0, 15.0, value=d["guidance"], step=0.5,
                help="높을수록 프롬프트에 충실 / 낮을수록 이미지 표현 자유",
            )

            if d["ip_scale"] is not None:
                settings.LOCAL_IP_ADAPTER_SCALE = st.slider(
                    "IP-Adapter Scale", 0.0, 1.0, value=d["ip_scale"], step=0.05,
                    help="높을수록 참조 이미지 스타일 강하게 반영 (0.8+ 권장)",
                )

            if d["strength"] is not None:
                settings.LOCAL_IMG2IMG_STRENGTH = st.slider(
                    "img2img Strength", 0.1, 1.0, value=d["strength"], step=0.05,
                    help="낮을수록 원본 구조 보존 (0.4 권장) / 높을수록 자유 재생성",
                )

            if d["ip_scale"] is not None:
                st.markdown("#### 가중치 파일")
                current_weight = settings.LOCAL_IP_ADAPTER_WEIGHT_NAME
                weight_index = list(_WEIGHT_OPTIONS.values()).index(
                    current_weight if current_weight in _WEIGHT_OPTIONS.values()
                    else "ip-adapter_sd15.bin"
                )
                selected_weight = st.selectbox(
                    "IP-Adapter 가중치",
                    list(_WEIGHT_OPTIONS.keys()),
                    index=weight_index,
                )
                settings.LOCAL_IP_ADAPTER_WEIGHT_NAME = _WEIGHT_OPTIONS[selected_weight]
        else:
            st.markdown("#### 모델 선택")
            current_image_model = getattr(
                settings,
                "IMAGE_MODEL",
                "stabilityai/stable-diffusion-xl-base-1.0",
            )
            model_options = dict(_HF_MODEL_OPTIONS)
            if current_image_model not in model_options.values():
                model_options = {
                    f"사용자 지정 ({current_image_model})": current_image_model,
                    **model_options,
                }

            selected_model_label = st.selectbox(
                "Hugging Face 모델",
                list(model_options.keys()),
                index=list(model_options.values()).index(current_image_model),
                help="원격 워커 모드에서는 이 선택값이 요청마다 전달됩니다.",
            )
            settings.IMAGE_MODEL = model_options[selected_model_label]

        st.divider()
        st.caption(f"모드: {'🟢 로컬' if use_local else '☁️ API'}")
