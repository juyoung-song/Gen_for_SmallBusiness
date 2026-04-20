"""GeneratedUpload CRUD 서비스.

docs/schema.md §3.6 기준:
- create(): 업로드 시도 레코드 생성 (instagram_post_id=None)
- mark_posted(): 게시 성공 시 instagram_post_id + posted_at 갱신
- list_published(): 인스타 게시 완료된 것만 (참조 이미지 풀 — reference gallery 소스)
- list_for_generation(): 특정 generation 의 업로드 이력 (feed/story 둘 다)
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.generated_upload import GeneratedUpload
from models.generation import Generation
from models.generation_output import GenerationOutput


class UploadService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        generation_output_id: UUID,
        kind: str,
        caption: str = "",
    ) -> GeneratedUpload:
        """업로드 시도 레코드 생성.

        kind 는 'feed' 또는 'story'. 스토리는 caption 이 빈 문자열.
        """
        if kind not in {"feed", "story"}:
            raise ValueError(f"지원하지 않는 upload kind: {kind}")

        upload = GeneratedUpload(
            generation_output_id=generation_output_id,
            kind=kind,
            caption=caption,
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
        upload = await self.session.get(GeneratedUpload, upload_id)
        if upload is None:
            raise ValueError(f"GeneratedUpload {upload_id} 가 존재하지 않습니다.")

        upload.instagram_post_id = instagram_post_id
        upload.posted_at = posted_at
        await self.session.commit()
        await self.session.refresh(upload)
        return upload

    async def list_published(
        self, brand_id: UUID | None = None
    ) -> list[tuple[GeneratedUpload, GenerationOutput]]:
        """인스타 게시 완료된 업로드 + 원본 GenerationOutput 쌍 목록.

        reference gallery 에서 이미지 경로(`GenerationOutput.content_path`) 와
        캡션(`GeneratedUpload.caption`) 을 함께 표시해야 해서 tuple 로 반환.

        brand_id 주어지면 해당 브랜드의 업로드만. (generation → brand 조인)
        """
        stmt = (
            select(GeneratedUpload, GenerationOutput)
            .join(GenerationOutput, GenerationOutput.id == GeneratedUpload.generation_output_id)
            .where(GeneratedUpload.instagram_post_id.is_not(None))
            .order_by(GeneratedUpload.posted_at.desc())
        )
        if brand_id is not None:
            stmt = stmt.join(
                Generation, Generation.id == GenerationOutput.generation_id
            ).where(Generation.brand_id == brand_id)

        result = await self.session.execute(stmt)
        return [(u, o) for u, o in result.all()]

    async def list_for_generation(
        self, generation_id: UUID
    ) -> list[GeneratedUpload]:
        """특정 generation 의 업로드 이력 (feed/story 둘 다 포함)."""
        stmt = (
            select(GeneratedUpload)
            .join(GenerationOutput, GenerationOutput.id == GeneratedUpload.generation_output_id)
            .where(GenerationOutput.generation_id == generation_id)
            .order_by(GeneratedUpload.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
