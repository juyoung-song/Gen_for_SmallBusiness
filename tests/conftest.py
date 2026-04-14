"""공용 pytest fixtures.

테스트는 In-memory SQLite + async 세션을 사용한다.
각 테스트 함수마다 새 engine/session 을 만들어 격리를 보장한다.
"""

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.database import attach_sqlite_fk_listener
from models.base import Base


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """테스트용 in-memory SQLite 세션.

    각 테스트가 시작될 때 모든 테이블을 새로 생성하고
    종료 시 엔진을 dispose 해서 테스트 간 완전 격리.

    SQLite 는 외래키 cascade 가 기본 OFF 이므로 production 과 동일한
    공용 헬퍼 (config.database.attach_sqlite_fk_listener) 를 사용한다.
    """
    # 각 테스트마다 독립적인 in-memory DB
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    attach_sqlite_fk_listener(engine)

    # 모든 모델을 import 해서 metadata 에 등록
    # (신규 모델 추가 시 이 블록에 import 추가)
    import models.brand  # noqa: F401
    import models.generated_upload  # noqa: F401
    import models.generation  # noqa: F401
    import models.generation_output  # noqa: F401
    import models.instagram_connection  # noqa: F401
    import models.reference_image  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def brand_factory(db_session):
    """Brand 생성 헬퍼. 필요한 최소 필드만 기본값 채워 반환."""
    from models.brand import Brand

    async def _create(
        *,
        name: str = "구름 베이커리",
        color_hex: str = "#5562EA",
        logo_path: str | None = None,
        style_prompt: str = "이 브랜드는 따뜻한 베이커리입니다.",
        instagram_account_id: str | None = None,
        instagram_username: str | None = None,
    ) -> Brand:
        brand = Brand(
            name=name,
            color_hex=color_hex,
            logo_path=logo_path,
            input_instagram_url="https://instagram.com/ref",
            input_description="작은 동네 베이커리",
            input_mood="따뜻하고 단정한",
            style_prompt=style_prompt,
            instagram_account_id=instagram_account_id,
            instagram_username=instagram_username,
        )
        db_session.add(brand)
        await db_session.commit()
        await db_session.refresh(brand)
        return brand

    return _create
