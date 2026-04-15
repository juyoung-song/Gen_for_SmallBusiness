"""런타임 데이터 경로 해석 헬퍼.

운영 환경에서는 repo 내부 `data/` 대신 외부 고정 경로를 쓰고 싶을 수 있다.
이 모듈은 아래 우선순위로 경로를 정한다.

1. `SQLITE_DB_PATH` 가 있으면 DB 파일은 그 경로 사용
2. 아니면 `APP_DATA_DIR/history.db`
3. `APP_DATA_DIR` 가 없으면 기본값은 `<repo>/data`

이미지/온보딩/staging 파일도 모두 `APP_DATA_DIR` 기준으로 저장된다.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = ROOT_DIR / "data"


def _resolve_path(raw: str) -> Path:
    return Path(raw).expanduser().resolve()


def get_app_data_dir() -> Path:
    """앱 데이터 루트 디렉토리 반환."""
    configured = os.getenv("APP_DATA_DIR", "").strip()
    data_dir = _resolve_path(configured) if configured else DEFAULT_DATA_DIR.resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_sqlite_db_path() -> Path:
    """SQLite DB 파일 경로 반환."""
    configured = os.getenv("SQLITE_DB_PATH", "").strip()
    db_path = _resolve_path(configured) if configured else get_app_data_dir() / "history.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path
