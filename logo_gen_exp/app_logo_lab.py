"""Streamlit 로고 생성 실험 페이지.

실행:
    streamlit run logo_gen_exp/app_logo_lab.py

메인 `app.py` 와 완전 분리된 독립 실행 페이지.

두 가지 생성 모드 비교:
- 🧠 AI 모델 (gpt-image-1-mini) — 프롬프트 기반 생성 + Langfuse trace
- 🔤 PIL 폰트 렌더링 — TTF 폰트로 로컬 렌더 (비용 0, 결정적, 한글 정확)
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

# 프로젝트 루트를 sys.path 에 추가 (streamlit run 으로 직접 실행 대응)
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from logo_gen_exp.generator import LogoGenerator  # noqa: E402
from logo_gen_exp.openai_client import OpenAIImageClient  # noqa: E402
from logo_gen_exp.pil_plus_ai import PilPlusAiEditor  # noqa: E402
from logo_gen_exp.pil_renderer import render_wordmark  # noqa: E402
from logo_gen_exp.prompts import (  # noqa: E402
    build_edit_prompt,
    build_logo_generation_prompt,
)

logger = logging.getLogger(__name__)

_EXP_DIR = Path(__file__).resolve().parent
_SAMPLES_DIR = _EXP_DIR / "samples"
_SAMPLES_DIR.mkdir(exist_ok=True)


# ══════════════════════════════════════════════
# 페이지 설정
# ══════════════════════════════════════════════
st.set_page_config(page_title="🧪 Logo Lab", page_icon="🧪", layout="wide")
st.title("🧪 로고 생성 실험실")
st.caption(
    "브랜드 이름 + 색상만으로 로고를 만드는 실험 공간. "
    "AI 모델과 로컬 폰트 렌더링 두 방식을 비교할 수 있습니다."
)


# ══════════════════════════════════════════════
# 사이드바
# ══════════════════════════════════════════════
with st.sidebar:
    st.markdown("### 🔑 환경 상태")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    lf_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    lf_host = os.environ.get("LANGFUSE_HOST", "(default cloud)")
    st.write("- OpenAI API Key:", "✅" if openai_key else "❌")
    st.write("- Langfuse Public Key:", "✅" if lf_key else "⚠️ 없음 (trace 비활성)")
    st.write(f"- Langfuse Host: `{lf_host}`")

    st.markdown("---")
    st.markdown("### 📂 샘플 폴더")
    st.code(str(_SAMPLES_DIR), language="text")


# ══════════════════════════════════════════════
# 입력 / 결과 2단 레이아웃
# ══════════════════════════════════════════════
col_input, col_result = st.columns([1, 1.5], gap="large")


def _list_ttf_fonts() -> list[Path]:
    return sorted(_EXP_DIR.glob("*.ttf"))


with col_input:
    st.markdown("### ✏️ 입력")

    # 모드 선택
    MODE_AI = "🧠 AI 모델 (gpt-image-1-mini)"
    MODE_PIL = "🔤 PIL 폰트 렌더링"
    MODE_EDIT = "🎨 PIL + AI 변형 (edit, 가드 O)"
    MODE_RAW = "🔥 Raw (PIL 베이스 + 내 프롬프트만, 가드 X)"
    mode = st.radio(
        "생성 모드",
        options=[MODE_AI, MODE_PIL, MODE_EDIT, MODE_RAW],
        horizontal=False,
        key="mode_radio",
    )
    is_ai_mode = mode == MODE_AI
    is_pil_mode = mode == MODE_PIL
    is_edit_mode = mode == MODE_EDIT
    is_raw_mode = mode == MODE_RAW

    name = st.text_input(
        "브랜드 이름",
        value=st.session_state.get("last_name", "goorm"),
        placeholder="예: goorm / 구름 / GOORM 구름",
        key="name_input",
    )
    color_hex = st.color_picker(
        "브랜드 색상",
        value=st.session_state.get("last_color", "#5562EA"),
        key="color_input",
    )

    # 모드별 추가 옵션
    selected_font_path: Path | None = None
    override_prompt = ""
    edit_instruction = ""

    if is_ai_mode:
        override_prompt = st.text_area(
            "✏️ 프롬프트 직접 수정 (선택)",
            value="",
            height=180,
            placeholder=(
                "비워두면 build_logo_generation_prompt 의 기본 프롬프트를 사용합니다. "
                "값을 넣으면 그 프롬프트가 그대로 모델에 들어갑니다 (실험용)."
            ),
        )
    else:
        # PIL / Edit / Raw 모드 모두 폰트 선택 필요
        fonts = _list_ttf_fonts()
        if not fonts:
            st.error(f"`{_EXP_DIR}` 에 .ttf 폰트 파일이 없습니다.")
        else:
            default_idx = 0
            for i, p in enumerate(fonts):
                if p.name == "LXGWWenKaiKR-Medium.ttf":
                    default_idx = i
                    break
            selected_font_path = st.selectbox(
                "폰트 선택",
                options=fonts,
                index=default_idx,
                format_func=lambda p: p.name,
                key="font_select",
            )

    if is_edit_mode:
        edit_instruction = st.text_area(
            "🎨 AI 변형 지시 (필수)",
            value="",
            height=140,
            placeholder=(
                "예: 자간 좁히기 / 첫 글자만 크게 / 필기체풍으로 기울임. "
                "시스템 가드가 자동으로 '배경 순백·장식 금지·글자 보존' 규칙을 추가합니다."
            ),
            key="edit_instruction_input",
        )

    raw_prompt_value = ""
    if is_raw_mode:
        raw_prompt_value = st.text_area(
            "🔥 Raw 프롬프트 (시스템 가드 없이 그대로 전달)",
            value="",
            height=180,
            placeholder=(
                "입력한 텍스트가 그대로 gpt-image-1-mini images.edit 의 prompt 로 들어갑니다. "
                "가드(배경 순백·장식 금지 등) 가 전혀 적용되지 않음에 유의. "
                "시스템 프롬프트와의 A/B 비교용."
            ),
            key="raw_prompt_input",
        )

    generate_disabled = (
        not name.strip()
        or (is_ai_mode and not openai_key)
        or (is_pil_mode and selected_font_path is None)
        or (
            is_edit_mode
            and (
                not openai_key
                or selected_font_path is None
                or not edit_instruction.strip()
            )
        )
        or (
            is_raw_mode
            and (
                not openai_key
                or selected_font_path is None
                or not raw_prompt_value.strip()
            )
        )
    )
    generate_clicked = st.button(
        "✨ 로고 생성",
        type="primary",
        use_container_width=True,
        disabled=generate_disabled,
    )
    if (is_ai_mode or is_edit_mode or is_raw_mode) and not openai_key:
        st.warning("OPENAI_API_KEY 가 .env 에 설정되어 있어야 AI / Edit / Raw 모드 실행 가능합니다.")
    if is_edit_mode and selected_font_path is not None and not edit_instruction.strip():
        st.info("🎨 Edit 모드는 AI 변형 지시가 필수입니다.")
    if is_raw_mode and selected_font_path is not None and not raw_prompt_value.strip():
        st.info("🔥 Raw 모드는 프롬프트가 필수입니다.")


# ══════════════════════════════════════════════
# 생성 실행
# ══════════════════════════════════════════════
with col_result:
    st.markdown("### 🎨 결과")

    if generate_clicked:
        try:
            png_bytes: bytes
            actual_prompt: str
            trace_id: str | None = None
            meta_extra: dict = {}

            if is_ai_mode:
                # ── AI 모드 ──
                default_prompt = build_logo_generation_prompt(
                    name=name.strip(), color_hex=color_hex
                )
                actual_prompt = override_prompt.strip() or default_prompt

                with st.spinner("⏳ gpt-image-1-mini 생성 중..."):
                    client = OpenAIImageClient(api_key=openai_key)
                    if override_prompt.strip():
                        png_bytes = client.generate_png(
                            prompt=override_prompt.strip(), size="1024x1024"
                        )
                    else:
                        generator = LogoGenerator(client=client)
                        png_bytes = generator.generate(
                            name=name.strip(), color_hex=color_hex
                        )
                    trace_id = client.last_trace_id
                    meta_extra["mode"] = "ai"
                    meta_extra["model"] = client.model
            elif is_edit_mode:
                # ── PIL + AI 변형 모드 (가드 있음) ──
                with st.spinner("⏳ PIL 렌더링 → gpt-image-1-mini edit 중..."):
                    client = OpenAIImageClient(api_key=openai_key)
                    editor = PilPlusAiEditor(
                        client=client,
                        font_path=selected_font_path,  # type: ignore[arg-type]
                    )
                    png_bytes = editor.edit(
                        name=name.strip(),
                        color_hex=color_hex,
                        user_instruction=edit_instruction.strip(),
                    )
                    trace_id = client.last_trace_id
                    actual_prompt = build_edit_prompt(
                        user_instruction=edit_instruction.strip()
                    )
                    meta_extra["mode"] = "pil_plus_ai_edit"
                    meta_extra["model"] = client.model
                    meta_extra["font"] = (
                        selected_font_path.name if selected_font_path else None
                    )
                    meta_extra["user_instruction"] = edit_instruction.strip()
            elif is_raw_mode:
                # ── Raw 모드: PIL 베이스 + 사용자 프롬프트 그대로 (가드 없음) ──
                with st.spinner("⏳ PIL 렌더링 → gpt-image-1-mini edit (raw) 중..."):
                    base_png = render_wordmark(
                        name=name.strip(),
                        color_hex=color_hex,
                        font_path=selected_font_path,  # type: ignore[arg-type]
                    )
                    client = OpenAIImageClient(api_key=openai_key)
                    png_bytes = client.edit_png(
                        image=base_png,
                        prompt=raw_prompt_value.strip(),
                        size="1024x1024",
                        span_name="logo.raw_edit",
                    )
                    trace_id = client.last_trace_id
                    actual_prompt = raw_prompt_value.strip()
                    meta_extra["mode"] = "raw_edit"
                    meta_extra["model"] = client.model
                    meta_extra["font"] = (
                        selected_font_path.name if selected_font_path else None
                    )
                    meta_extra["user_instruction"] = raw_prompt_value.strip()
            else:
                # ── PIL 모드 ──
                with st.spinner("⏳ PIL 로컬 렌더링 중..."):
                    png_bytes = render_wordmark(
                        name=name.strip(),
                        color_hex=color_hex,
                        font_path=selected_font_path,  # type: ignore[arg-type]
                    )
                actual_prompt = (
                    f"[PIL 렌더링] font={selected_font_path.name if selected_font_path else '?'} "
                    f"name={name!r} color={color_hex}"
                )
                meta_extra["mode"] = "pil"
                meta_extra["font"] = (
                    selected_font_path.name if selected_font_path else None
                )

            # 파일 저장
            stem = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
            png_path = _SAMPLES_DIR / f"{stem}.png"
            meta_path = _SAMPLES_DIR / f"{stem}.json"
            png_path.write_bytes(png_bytes)
            meta_path.write_text(
                json.dumps(
                    {
                        "name": name.strip(),
                        "color_hex": color_hex,
                        "prompt": actual_prompt,
                        "trace_id": trace_id,
                        "created_at": datetime.now().isoformat(),
                        **meta_extra,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            # 세션 저장
            st.session_state.last_name = name.strip()
            st.session_state.last_color = color_hex
            st.session_state.last_bytes = png_bytes
            st.session_state.last_prompt = actual_prompt
            st.session_state.last_trace_id = trace_id
            st.session_state.last_path = str(png_path)
            st.session_state.last_mode = meta_extra["mode"]

        except Exception as e:  # noqa: BLE001
            logger.exception("로고 생성 실패")
            st.error(f"❌ 생성 실패: {type(e).__name__}: {e}")
            with st.expander("🔍 기술 상세", expanded=False):
                st.exception(e)

    # 최근 결과 표시
    if "last_bytes" in st.session_state:
        mode_badge = {
            "ai": "🧠 AI",
            "pil": "🔤 PIL",
            "pil_plus_ai_edit": "🎨 PIL+Edit",
            "raw_edit": "🔥 Raw",
        }.get(st.session_state.get("last_mode"), "?")
        st.image(
            st.session_state.last_bytes,
            caption=f"{mode_badge} · {st.session_state.last_name} · {st.session_state.last_color}",
            width="stretch",
        )
        st.caption(f"📁 saved → `{st.session_state.last_path}`")

        if st.session_state.get("last_trace_id"):
            st.info(f"🔗 Langfuse trace_id: `{st.session_state.last_trace_id}`")

        with st.expander("📜 사용된 프롬프트 / 파라미터", expanded=False):
            st.code(st.session_state.last_prompt, language="text")
    else:
        st.info("왼쪽에 입력 후 **✨ 로고 생성** 을 눌러주세요.")


# ══════════════════════════════════════════════
# 최근 샘플 히스토리
# ══════════════════════════════════════════════
st.markdown("---")
st.markdown("### 📚 최근 샘플 (최대 12개)")
recent = sorted(
    _SAMPLES_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True
)[:12]
if not recent:
    st.caption("아직 생성된 샘플이 없어요.")
else:
    cols = st.columns(4)
    for idx, img_path in enumerate(recent):
        with cols[idx % 4]:
            meta_path = img_path.with_suffix(".json")
            meta: dict = {}
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    pass
            mode = meta.get("mode", "?")
            badge = {
                "ai": "🧠",
                "pil": "🔤",
                "pil_plus_ai_edit": "🎨",
                "raw_edit": "🔥",
            }.get(mode, "?")
            caption = (
                f"{badge} {meta.get('name', '?')} · {meta.get('color_hex', '?')}"
            )
            st.image(str(img_path), caption=caption, width="stretch")
