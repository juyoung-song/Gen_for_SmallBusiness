"""Staging + 브랜드 자산 파일 저장 유틸.

두 가지 저장 위치를 분리:

- STAGING_DIR (data/staging):
    사용자가 업로드한 raw 이미지 등 임시 파일.
    design.md §4.4 의 "파일은 즉시 staging 저장" 정책 지원.
    추후 permanent 로 이동되거나 정리될 수 있음.

- BRAND_ASSETS_DIR (data/brand):
    온보딩에서 저장되는 영구 브랜드 자산 (로고 등).
    브랜드 생존 기간 동안 유지.

두 함수 모두 UUID 기반 파일명 + 디렉토리 자동 생성.
"""

from pathlib import Path
from uuid import uuid4

from config.runtime_paths import get_app_data_dir

_DATA_DIR = get_app_data_dir()

# 임시 파일 (업로드 raw 이미지 등)
STAGING_DIR: Path = _DATA_DIR / "staging"

# 영구 브랜드 자산 (로고 등)
BRAND_ASSETS_DIR: Path = _DATA_DIR / "brand"


def _save_to(dir_path: Path, data: bytes, extension: str) -> Path:
    """내부 공통 구현 — dir_path 에 UUID 파일명으로 저장."""
    dir_path.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{extension}"
    path = dir_path / filename
    path.write_bytes(data)
    return path


def save_to_staging(data: bytes, extension: str = ".jpg") -> Path:
    """업로드 바이트를 staging 디렉토리에 고유 이름으로 저장.

    Args:
        data: 저장할 바이너리
        extension: 파일 확장자 (.jpg, .png 등). 앞에 점 포함.

    Returns:
        저장된 파일의 절대 경로.
    """
    return _save_to(STAGING_DIR, data, extension)


def save_to_brand_assets(data: bytes, extension: str = ".png") -> Path:
    """브랜드 로고 등 영구 자산을 BRAND_ASSETS_DIR 에 저장.

    staging 과 달리 영구 보관 대상이라 정리 로직이 없음.

    Args:
        data: 저장할 바이너리
        extension: 기본값 .png (로고가 PNG 가 많음)
    """
    return _save_to(BRAND_ASSETS_DIR, data, extension)
