"""사이드바 UI — 개발자 전용 백엔드 토글 (Stage 2).

app.py 에서 `from ui.sidebar import render_sidebar_settings` 후
`render_sidebar_settings(settings)` 한 줄로 호출.

Stage 2 변경:
- IMAGE_BACKEND_KIND enum 4종을 dropdown 으로 즉시 전환
- HF_LOCAL 선택 시에만 LOCAL_BACKEND (ip_adapter / img2img / hybrid) + 파라미터 노출
- 사이드바는 **개발자 전용** 임을 캡션으로 명시. 모바일/배포 환경에서는 보이지 않거나
  관리자 인증 뒤에 둘 예정.
"""

import streamlit as st

from config.settings import ImageBackendKind

# 백엔드별 추천 기본값 (HF_LOCAL 모드의 LOCAL_BACKEND 세부 옵션)
# IP-Adapter: CLIP 임베딩으로 스타일 주입. scale 높여야 참조 반영 강해짐.
# img2img:    참조 이미지 직접 노이즈화 후 재생성. strength 낮을수록 원본 충실.
# hybrid:     img2img 베이스 위에 IP-Adapter 스타일 추가.
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

# 사용자에게 보여줄 라벨
_KIND_LABELS: dict[ImageBackendKind, str] = {
    ImageBackendKind.OPENAI_IMAGE: "🎨 OpenAI Image — gpt-image-1-mini (상품+로고 multi-input, CP15 기본)",
    ImageBackendKind.MOCK: "🧪 Mock — Pillow 그라데이션 (외부 호출 0)",
    ImageBackendKind.HF_LOCAL: "🖥️ HF Local — 같은 머신의 diffusers (Mac 느림)",
    ImageBackendKind.HF_REMOTE_API: "☁️ HF Remote API — Hugging Face Serverless",
    ImageBackendKind.REMOTE_WORKER: "📡 Remote Worker — 자체 VM 호출",
}


def render_sidebar_settings(settings) -> None:
    """사이드바에 백엔드 모드 + 로컬 모델 파라미터 UI 를 렌더링하고
    settings 객체를 직접 mutate 한다 (메모리상, .env 는 건드리지 않음)."""
    with st.sidebar:
        st.markdown("## ⚙️ 백엔드 설정")
        st.caption("👨‍💻 **개발자 전용**. 메모리 변경만 — streamlit 재시작 시 .env 값으로 돌아감.")

        # 1. 이미지 백엔드 모드 선택 (enum dropdown)
        st.markdown("#### 이미지 백엔드")
        kind_options = list(_KIND_LABELS.keys())
        kind_label_list = [_KIND_LABELS[k] for k in kind_options]
        current_kind: ImageBackendKind = settings.IMAGE_BACKEND_KIND
        try:
            current_index = kind_options.index(current_kind)
        except ValueError:
            current_index = 0

        selected_label = st.selectbox(
            "백엔드 모드",
            kind_label_list,
            index=current_index,
            label_visibility="collapsed",
            key="sidebar_image_backend_kind",
        )
        selected_kind = kind_options[kind_label_list.index(selected_label)]
        settings.IMAGE_BACKEND_KIND = selected_kind

        # 2. HF_LOCAL 모드일 때만 세부 옵션 표시
        if selected_kind == ImageBackendKind.HF_LOCAL:
            st.markdown("#### 로컬 백엔드 종류")
            backend_labels = {
                "IP-Adapter (스타일 주입)": "ip_adapter",
                "img2img (구조 보존)":      "img2img",
                "Hybrid (구조 + 스타일)":   "hybrid",
            }
            current_backend = getattr(settings, "LOCAL_BACKEND", "ip_adapter")
            selected_local_label = st.radio(
                "로컬 백엔드",
                list(backend_labels.keys()),
                index=list(backend_labels.values()).index(current_backend)
                    if current_backend in backend_labels.values() else 0,
                label_visibility="collapsed",
            )
            backend = backend_labels[selected_local_label]
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

        st.divider()
        st.caption(f"현재 모드: `{selected_kind.value}`")
