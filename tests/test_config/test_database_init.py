"""init_db() idempotent 동작 검증.

배경: Streamlit 환경에서 매 rerun 마다 init_db() 가 호출되어도 안전해야 한다.
이전에 `@st.cache_resource` 로 init_db 결과를 캐시했었는데, 모델 스키마가
변경된 후에도 캐시 때문에 새 테이블이 생성되지 않아 OperationalError 가
발생했다. 캐시를 제거하고 매번 호출해도 idempotent 가 보장돼야 한다.
"""

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine


def _table_names(engine_sync) -> list[str]:
    return inspect(engine_sync).get_table_names()


class TestInitDbIdempotent:
    def test_init_db_creates_all_tables(self, tmp_path, monkeypatch):
        """첫 호출에 신규 스키마 6개 테이블이 모두 생성된다."""
        # 임시 DB 파일로 격리
        db_path = tmp_path / "test.db"
        db_url = f"sqlite+aiosqlite:///{db_path}"
        test_engine = create_async_engine(db_url)

        monkeypatch.setattr("config.database.engine", test_engine)

        from config.database import init_db
        asyncio.run(init_db())

        # 동기 엔진으로 inspect
        from sqlalchemy import create_engine
        sync_engine = create_engine(f"sqlite:///{db_path}")
        tables = _table_names(sync_engine)
        sync_engine.dispose()

        assert "brands" in tables
        assert "reference_images" in tables
        assert "generations" in tables
        assert "generation_outputs" in tables
        assert "instagram_connections" in tables
        assert "generated_uploads" in tables

    def test_init_db_is_idempotent_when_called_twice(self, tmp_path, monkeypatch):
        """두 번 연속 호출해도 에러 없이 같은 테이블 집합."""
        db_path = tmp_path / "test.db"
        db_url = f"sqlite+aiosqlite:///{db_path}"
        test_engine = create_async_engine(db_url)
        monkeypatch.setattr("config.database.engine", test_engine)

        from config.database import init_db
        asyncio.run(init_db())
        asyncio.run(init_db())  # 두 번째 — 캐시 없이 매번 호출되는 시나리오

        from sqlalchemy import create_engine
        sync_engine = create_engine(f"sqlite:///{db_path}")
        tables = _table_names(sync_engine)
        sync_engine.dispose()

        assert "brands" in tables
        assert "reference_images" in tables
        assert "generations" in tables
        assert "generation_outputs" in tables
        assert "instagram_connections" in tables
        assert "generated_uploads" in tables
