"""DB의 History 테이블과 통신하는 서비스 레이어."""

import os
import uuid

from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.history import History, GenerationType
from schemas.history_schema import HistoryCreate, HistoryResponse


class HistoryService:
    """광고 생성 히스토리 데이터베이스 접근 클래스."""

    def __init__(self, db: Optional[AsyncSession] = None) -> None:
        self.db = db

    async def save_history(self, create_data: HistoryCreate) -> HistoryResponse:
        """새 히스토리 레코드를 DB에 삽입.
        
        세션이 주입되지 않았다면 스스로 생성하여 실행하며, 익셉션 발생 시 롤백을 보장합니다.
        """
        if self.db:
            return await self._save_history_impl(self.db, create_data)
        
        from config.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await self._save_history_impl(session, create_data)

    async def _save_history_impl(self, session: AsyncSession, create_data: HistoryCreate) -> HistoryResponse:
        """실제 저장 로직 집약부 및 트랜잭션 관리."""
        try:
            result_payload = create_data.result_data.copy()

            # 이미지는 로컬에 저장하고 경로만 남김
            if create_data.generation_type in (GenerationType.IMAGE, GenerationType.COMBINED) and "image_data" in result_payload:
                image_bytes = result_payload.pop("image_data")
                if image_bytes:
                    filename = f"{uuid.uuid4()}.png"
                    img_dir = "./data/images"
                    os.makedirs(img_dir, exist_ok=True)
                    filepath = os.path.join(img_dir, filename)
                    
                    with open(filepath, "wb") as f:
                        f.write(image_bytes)
                    
                    result_payload["image_path"] = filepath

            history = History(
                generation_type=create_data.generation_type,
                product_name=create_data.product_name,
                description=create_data.description,
                style=create_data.style,
                result_data=result_payload,
            )

            session.add(history)
            await session.commit()
            await session.refresh(history)

            return HistoryResponse.model_validate(history)
        except Exception:
            await session.rollback()
            raise

    async def get_all_histories(self) -> List[HistoryResponse]:
        """기존 히스토리를 최신순으로 모두 조회."""
        if self.db:
            return await self._get_all_impl(self.db)
            
        from config.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await self._get_all_impl(session)

    async def _get_all_impl(self, session: AsyncSession) -> List[HistoryResponse]:
        """실제 조회 실행 로직."""
        query = select(History).order_by(History.created_at.desc())
        result = await session.execute(query)
        histories = result.scalars().all()
        return [HistoryResponse.model_validate(h) for h in histories]
