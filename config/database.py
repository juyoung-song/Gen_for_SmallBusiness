"""비동기 데이터베이스 연결 및 엔진 설정.
- aiosqlite 드라이버 사용.
- 비동기 엔진, 비동기 로컬 세션 팩토리 제공.
"""

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# SQLite 데이터베이스 파일 경로 지정
DB_DIR = "./data"
os.makedirs(DB_DIR, exist_ok=True)
DB_URL = f"sqlite+aiosqlite:///{DB_DIR}/history.db"

# 비동기 엔진 생성
engine = create_async_engine(DB_URL, echo=False)

# 세션 팩토리 생성
AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """의존성 주입을 위한 비동기 세션 제너레이터."""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """애플리케이션 시작 시 DB 테이블 동기화(초기화) 진행."""
    from models.base import Base
    import models.history  # 모델 레지스트리 자동 등록을 위한 Import

    async with engine.begin() as conn:
        # DB 존재 안할 시 스키마 생성 (production에서는 alembic 권장)
        await conn.run_sync(Base.metadata.create_all)
