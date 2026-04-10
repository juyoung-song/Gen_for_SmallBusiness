"""GeneratedUpload CRUD 서비스.

design.md §4.4 / §4.5 / §6 기준:
- create(): 생성 결과를 staging 상태로 저장 (instagram_post_id=None)
- mark_posted(): 게시 성공 시 instagram_post_id + posted_at 갱신
- list_published(): 인스타 게시 완료된 것만 (참조 이미지 풀)
- list_for_product(): 특정 상품의 모든 결과물
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.generated_upload import GeneratedUpload


class UploadService:
    """GeneratedUpload CRUD 서비스."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        product_id: UUID,
        image_path: str,
        caption: str,
        goal_category: str,
        goal_freeform: str = "",
    ) -> GeneratedUpload:
        """생성 결과를 staging 상태로 저장 (인스타 메타 없음)."""
        upload = GeneratedUpload(
            product_id=product_id,
            image_path=image_path,
            caption=caption,
            goal_category=goal_category,
            goal_freeform=goal_freeform,
        )
        self.session.add(upload)
        await self.session.commit()
        await self.session.refresh(upload)
        return upload

    async def mark_posted(
        self,
        *,
        upload_id: UUID,
        instagram_post_id: str,
        posted_at: datetime,
    ) -> GeneratedUpload:
        """게시 성공 시 인스타 메타데이터 갱신.

        존재하지 않는 upload_id 면 ValueError.
        """
        upload = await self.session.get(GeneratedUpload, upload_id)
        if upload is None:
            raise ValueError(f"GeneratedUpload {upload_id} 가 존재하지 않습니다.")

        upload.instagram_post_id = instagram_post_id
        upload.posted_at = posted_at
        await self.session.commit()
        await self.session.refresh(upload)
        return upload

    async def list_published(self) -> list[GeneratedUpload]:
        """인스타 게시 완료된 항목만 (참조 이미지 풀)."""
        result = await self.session.execute(
            select(GeneratedUpload)
            .where(GeneratedUpload.instagram_post_id.is_not(None))
            .order_by(GeneratedUpload.posted_at.desc())
        )
        return list(result.scalars().all())

    async def list_for_product(
        self, product_id: UUID
    ) -> list[GeneratedUpload]:
        """특정 상품의 모든 결과물 (게시 여부 무관)."""
        result = await self.session.execute(
            select(GeneratedUpload)
            .where(GeneratedUpload.product_id == product_id)
            .order_by(GeneratedUpload.created_at)
        )
        return list(result.scalars().all())
