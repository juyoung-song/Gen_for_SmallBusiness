"""Production async engine 에 SQLite 외래키 PRAGMA 가 적용돼 있는지 검증.

배경 (코드리뷰 H2):
tests/conftest.py 의 in-memory 엔진은 PRAGMA foreign_keys=ON 을 이벤트
리스너로 걸어두지만, 정작 `config/database.py` 의 production engine 에는
해당 리스너가 없었다. 결과적으로 테스트는 통과하지만 실제 앱에서는 ORM
cascade / ondelete 가 조용히 동작하지 않는 production-only 버그가 생길 수
있다. 매 커넥션마다 FK 가 실제로 켜지는지 behavior 레벨로 확인한다.
"""

import asyncio

from sqlalchemy import text

from config.database import engine


class TestProductionEngineForeignKeys:
    def test_foreign_keys_pragma_is_enabled_on_connect(self):
        """production engine 이 새 커넥션에서 PRAGMA foreign_keys=1 을 리턴한다."""

        async def _probe() -> int:
            async with engine.connect() as conn:
                result = await conn.execute(text("PRAGMA foreign_keys"))
                row = result.first()
                return int(row[0]) if row else -1

        value = asyncio.run(_probe())
        assert value == 1, (
            "production engine 에 FK PRAGMA 가 켜져 있지 않음. "
            "config/database.py 의 engine 에 connect 리스너 필요."
        )
