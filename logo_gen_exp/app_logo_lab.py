"""Streamlit 로고 생성 실험 페이지.

실행:
    streamlit run logo_gen_exp/app_logo_lab.py

메인 `app.py` 와 완전 분리된 독립 실행 페이지. 실제 OpenAI 호출 + Langfuse trace.

입력:  브랜드 이름 / 색상 / (선택) 프롬프트 오버라이드
결과:  생성 이미지 + 사용 프롬프트 + Langfuse trace_id + samples/ 저장
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

# 프로젝트 루트를 sys.path 에 추가. streamlit 으로 직접 실행 시
# 기본 sys.path 는 파일이 위치한 logo_gen_exp/ 만 포함되어 logo_gen_exp 패키지 자체를
# import 할 수 없다. 상대 import 대신 절대 import 를 유지하기 위해 루트를 추가.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv()  # .env 로드

from logo_gen_exp.generator import LogoGenerator  # noqa: E402
from logo_gen_exp.openai_client import OpenAIImageClient  # noqa: E402
from logo_gen_exp.prompts import build_logo_generation_prompt  # noqa: E402

logger = logging.getLogger(__name__)

_EXP_DIR = Path(__file__).resolve().parent
_SAMPLES_DIR = _EXP_DIR / "samples"
_SAMPLES_DIR.mkdir(exist_ok=True)


# ══════════════════════════════════════════════
# 페이지 설정
# ══════════════════════════════════════════════
st.set_page_config(
    page_title="🧪 Logo Lab",
    page_icon="🧪",
    layout="wide",
)

st.title("🧪 로고 생성 실험실")
st.caption(
    "브랜드 이름 + 색상만으로 AI 타이포그래피 로고를 생성하는 실험 공간입니다. "
    "메인 앱과 분리되어 있으며 실제 OpenAI(`gpt-image-1`) 호출 + Langfuse trace 기록이 일어납니다."
)


# ══════════════════════════════════════════════
# 사이드바: 환경 상태
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
# 메인: 입력 폼
# ══════════════════════════════════════════════
col_input, col_result = st.columns([1, 1.5], gap="large")

with col_input:
    st.markdown("### ✏️ 입력")

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

    override_prompt = st.text_area(
        "✏️ 프롬프트 직접 수정 (선택)",
        value="",
        height=180,
        placeholder="비워두면 build_logo_generation_prompt 의 기본 프롬프트를 사용합니다. "
        "값을 넣으면 그 프롬프트가 그대로 모델에 들어갑니다 (실험용).",
        help="프롬프트 변형 실험용. 비워두면 기본 빌더 함수 결과를 사용.",
    )

    generate_clicked = st.button(
        "✨ 로고 생성",
        type="primary",
        use_container_width=True,
        disabled=not (openai_key and name.strip()),
    )

    if not openai_key:
        st.warning("OPENAI_API_KEY 가 .env 에 설정되어 있어야 실행됩니다.")


with col_result:
    st.markdown("### 🎨 결과")

    if generate_clicked:
        # 기본 프롬프트 계산 (표시용)
        default_prompt = build_logo_generation_prompt(
            name=name.strip(), color_hex=color_hex
        )
        actual_prompt = override_prompt.strip() or default_prompt

        with st.spinner("⏳ gpt-image-1 이미지 생성 중... (10~30초 소요)"):
            try:
                client = OpenAIImageClient(api_key=openai_key)

                if override_prompt.strip():
                    # 오버라이드: generator 우회 — 프롬프트 그대로 모델에 전달
                    png_bytes = client.generate_png(
                        prompt=override_prompt.strip(), size="1024x1024"
                    )
                else:
                    # 정상 경로: LogoGenerator 통과
                    generator = LogoGenerator(client=client)
                    png_bytes = generator.generate(
                        name=name.strip(), color_hex=color_hex
                    )

                trace_id = client.last_trace_id

                # samples 에 저장 (+ 메타)
                stem = (
                    f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    f"_{uuid4().hex[:6]}"
                )
                png_path = _SAMPLES_DIR / f"{stem}.png"
                meta_path = _SAMPLES_DIR / f"{stem}.json"
                png_path.write_bytes(png_bytes)
                meta_path.write_text(
                    json.dumps(
                        {
                            "name": name.strip(),
                            "color_hex": color_hex,
                            "override_used": bool(override_prompt.strip()),
                            "prompt": actual_prompt,
                            "trace_id": trace_id,
                            "model": client.model,
                            "created_at": datetime.now().isoformat(),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

                # 세션에 최신 결과 저장
                st.session_state.last_name = name.strip()
                st.session_state.last_color = color_hex
                st.session_state.last_bytes = png_bytes
                st.session_state.last_prompt = actual_prompt
                st.session_state.last_trace_id = trace_id
                st.session_state.last_path = str(png_path)

            except Exception as e:  # noqa: BLE001
                logger.exception("로고 생성 실패")
                st.error(f"❌ 생성 실패: {type(e).__name__}: {e}")
                with st.expander("🔍 기술 상세", expanded=False):
                    st.exception(e)

    # 세션에 저장된 마지막 결과 표시
    if "last_bytes" in st.session_state:
        st.image(
            st.session_state.last_bytes,
            caption=f"{st.session_state.last_name} · {st.session_state.last_color}",
            width="stretch",
        )
        st.caption(f"📁 saved → `{st.session_state.last_path}`")

        trace_id = st.session_state.get("last_trace_id")
        if trace_id:
            st.info(f"🔗 Langfuse trace_id: `{trace_id}`")
        else:
            st.caption("_(Langfuse trace 비활성 또는 미기록)_")

        with st.expander("📜 사용된 프롬프트", expanded=False):
            st.code(st.session_state.last_prompt, language="text")
    else:
        st.info("왼쪽에 입력 후 **✨ 로고 생성** 을 눌러주세요.")


# ══════════════════════════════════════════════
# 하단: 이전 샘플 히스토리
# ══════════════════════════════════════════════
st.markdown("---")
st.markdown("### 📚 최근 샘플 (최대 12개)")

recent = sorted(_SAMPLES_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)[:12]
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
            caption = f"{meta.get('name', '?')} · {meta.get('color_hex', '?')}"
            st.image(str(img_path), caption=caption, width="stretch")
