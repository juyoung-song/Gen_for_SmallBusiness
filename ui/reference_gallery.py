"""참조 이미지 갤러리 — 이전 광고 결과물 풀에서 다중 선택.

docs/schema.md §3.4/3.6 기준:
- 풀 범위: 게시 완료된 GeneratedUpload (instagram_post_id != NULL)
- 이미지 경로: GenerationOutput.content_path (upload 는 FK 만 가짐)
- UI: 썸네일 갤러리 (드롭다운 불가 — 시각적 결정)
- 옵션: 선택 안 해도 광고 생성 가능

세션 상태:
- `reference_selected_ids`: 선택된 GenerationOutput.id 의 set (str 형태)
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from config.database import AsyncSessionLocal
from models.generated_upload import GeneratedUpload
from models.generation_output import GenerationOutput
from services.upload_service import UploadService
from utils.async_runner import run_async

_GALLERY_COLS = 3
_MAX_DISPLAY = 24


def render_reference_gallery() -> list[str]:
    """참조 이미지 갤러리를 렌더링하고 선택된 파일 경로들을 반환한다.

    Returns:
        선택된 GenerationOutput 의 content_path 리스트 (빈 리스트 가능).
    """
    if "reference_selected_ids" not in st.session_state:
        st.session_state.reference_selected_ids = set()

    pairs = _fetch_published_pairs()

    if not pairs:
        st.info(
            "🎨 아직 올린 광고가 없어요. 광고를 몇 번 만들고 인스타에 올리면 "
            "여기에 모여서 다음 광고의 참조로 쓸 수 있어요."
        )
        return []

    st.caption(
        f"이전에 올린 광고 중 비슷한 톤으로 가고 싶은 걸 골라주세요 (선택, 다중 가능). "
        f"총 {len(pairs)}장 · 최근 {min(len(pairs), _MAX_DISPLAY)}장 표시."
    )

    display_pairs = pairs[:_MAX_DISPLAY]
    selected_ids: set[str] = set(st.session_state.reference_selected_ids)

    for row_start in range(0, len(display_pairs), _GALLERY_COLS):
        cols = st.columns(_GALLERY_COLS)
        for col_i, (upload, output) in enumerate(
            display_pairs[row_start : row_start + _GALLERY_COLS]
        ):
            with cols[col_i]:
                _render_gallery_card(upload, output, selected_ids)

    st.session_state.reference_selected_ids = selected_ids

    # 선택된 output id → content_path
    selected_paths = [
        o.content_path
        for _, o in pairs
        if str(o.id) in selected_ids and o.content_path
    ]

    if selected_paths:
        st.success(f"✅ 참조 이미지 {len(selected_paths)}장 선택됨")

    return selected_paths


def _render_gallery_card(
    upload: GeneratedUpload,
    output: GenerationOutput,
    selected_ids: set[str],
) -> None:
    """한 장의 썸네일 카드 + 선택 토글."""
    output_id_str = str(output.id)
    is_selected = output_id_str in selected_ids

    if output.content_path:
        path = Path(output.content_path)
        if path.exists():
            st.image(
                str(path),
                caption=_short_caption(upload.caption),
                width="stretch",
            )
        else:
            st.warning(f"❓ {path.name} 파일 없음")
    else:
        st.warning("❓ 이미지 경로 없음")

    checkbox_label = "✅ 선택됨" if is_selected else "선택하기"
    new_state = st.checkbox(
        checkbox_label,
        value=is_selected,
        key=f"ref_select_{output_id_str}",
    )
    if new_state and not is_selected:
        selected_ids.add(output_id_str)
    elif not new_state and is_selected:
        selected_ids.discard(output_id_str)


def _short_caption(caption: str, max_len: int = 30) -> str:
    if not caption:
        return ""
    flat = caption.replace("\n", " ")
    return flat if len(flat) <= max_len else flat[: max_len - 1] + "…"


def _fetch_published_pairs() -> list[tuple[GeneratedUpload, GenerationOutput]]:
    """게시 완료된 (upload, output) 쌍 전체."""

    async def _fetch() -> list[tuple[GeneratedUpload, GenerationOutput]]:
        async with AsyncSessionLocal() as session:
            service = UploadService(session)
            return await service.list_published()

    return run_async(_fetch())
