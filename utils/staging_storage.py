"""Staging 파일 저장 유틸.

design.md §4.4 의 하이브리드 저장 정책을 지원:
- 사용자가 업로드한 파일은 **즉시** staging 디렉토리에 저장 (손실 방지)
- DB row 등 메타데이터는 생성 후 백그라운드 태스크에서 처리

staging → permanent 이동은 별도 작업 (추후).
"""

from pathlib import Path
from uuid import uuid4

# 프로젝트 루트 기준 data/staging. 테스트에서 monkeypatch 가능.
STAGING_DIR: Path = (
    Path(__file__).resolve().parent.parent / "data" / "staging"
)


def save_to_staging(data: bytes, extension: str = ".jpg") -> Path:
    """바이트를 staging 디렉토리에 고유한 이름으로 저장하고 경로 반환.

    Args:
        data: 저장할 바이너리
        extension: 파일 확장자 (.jpg, .png 등). 앞에 점 포함.

    Returns:
        저장된 파일의 절대 경로.
    """
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{extension}"
    path = STAGING_DIR / filename
    path.write_bytes(data)
    return path
