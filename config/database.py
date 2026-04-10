"""비동기 데이터베이스 연결 및 엔진 설정.
- aiosqlite 드라이버 사용.
- 비동기 엔진, 비동기 로컬 세션 팩토리 제공.
"""

from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# SQLite 데이터베이스 파일 경로 — 프로젝트 루트 기준 절대경로 (S-1)
# 실행 디렉토리에 의존하지 않도록 __file__ 기준으로 잡는다.
DB_DIR = Path(__file__).resolve().parent.parent / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_URL = f"sqlite+aiosqlite:///{DB_DIR / 'history.db'}"


def attach_sqlite_fk_listener(async_engine) -> None:
    """SQLite 외래키 cascade 를 위한 PRAGMA 리스너를 async engine 에 부착한다.

    SQLite 는 기본값이 FK OFF 라서 매 connect 시 PRAGMA 로 켜줘야 한다.
    production engine (config/database.py) 과 테스트용 in-memory 엔진
    (tests/conftest.py) 모두 동일 리스너가 필요하므로 공용 헬퍼로 분리.
    """

    @event.listens_for(async_engine.sync_engine, "connect")
    def _enable_sqlite_fk(dbapi_conn, _):  # pragma: no cover - trivial
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


# 비동기 엔진 생성 (+ FK PRAGMA 리스너 부착)
engine = create_async_engine(DB_URL, echo=False)
attach_sqlite_fk_listener(engine)

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
    # 모든 모델을 import 해서 metadata 에 등록
    # (`from models import ...` 한 줄로 신규 3종 + legacy 모두 로드)
    import models  # noqa: F401
    from models.base import Base

    async with engine.begin() as conn:
        # DB 존재 안할 시 스키마 생성 (production에서는 alembic 권장)
        await conn.run_sync(Base.metadata.create_all)
