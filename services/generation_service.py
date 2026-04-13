"""Generation CRUD + 조회 서비스.

docs/schema.md §3.3 / §3.4 기준:
- create_with_outputs(): Generation + 산출물들을 한 번에 INSERT
- list_products(): 상품군(distinct product_name) 목록 + 각 그룹의 대표 Generation
- list_all(): 모든 Generation 을 최신순으로
- mark_failed(): 실패 시 error_message 기록

docs/schema.md 의 설계 원칙상 Generation 은 append-only 다. update 메서드는 제공하지 않는다
(단, langfuse_trace_id 주입 / error_message 기록은 특별 허용).
"""

from dataclasses import dataclass
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.generation import Generation
from models.generation_output import GenerationOutput


@dataclass(frozen=True)
class OutputSpec:
    """create_with_outputs 에 넘기는 산출물 스펙."""

    kind: str
    content_text: str | None = None
    content_path: str | None = None


@dataclass(frozen=True)
class ProductGroup:
    """product_name 으로 그룹핑한 Generation 이력의 대표치.

    list_products() 반환 단위. 드롭다운 표시용.
    """

    product_name: str
    product_description: str
    product_image_path: str | None
    latest_generation_id: UUID
    generation_count: int


class GenerationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_with_outputs(
        self,
        *,
        brand_id: UUID,
        reference_image_id: UUID | None,
        product_name: str,
        product_description: str,
        product_image_path: str | None,
        goal: str,
        tone: str,
        is_new_product: bool,
        outputs: Sequence[OutputSpec],
        langfuse_trace_id: str | None = None,
    ) -> Generation:
        """Generation 하나 + 여러 GenerationOutput 을 단일 트랜잭션으로 저장."""
        generation = Generation(
            brand_id=brand_id,
            reference_image_id=reference_image_id,
            product_name=product_name.strip(),
            product_description=product_description,
            product_image_path=product_image_path,
            goal=goal,
            tone=tone,
            is_new_product=is_new_product,
            langfuse_trace_id=langfuse_trace_id,
        )
        self.session.add(generation)
        await self.session.flush()  # generation.id 확보

        for spec in outputs:
            self.session.add(
                GenerationOutput(
                    generation_id=generation.id,
                    kind=spec.kind,
                    content_text=spec.content_text,
                    content_path=spec.content_path,
                )
            )

        await self.session.commit()
        await self.session.refresh(generation)
        return generation

    async def mark_failed(self, generation_id: UUID, error_message: str) -> None:
        gen = await self.session.get(Generation, generation_id)
        if gen is None:
            return
        gen.error_message = error_message
        await self.session.commit()

    async def get_with_outputs(self, generation_id: UUID) -> Generation | None:
        stmt = (
            select(Generation)
            .where(Generation.id == generation_id)
            .options(selectinload(Generation.outputs))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_brand(
        self, brand_id: UUID, limit: int = 50
    ) -> list[Generation]:
        """특정 브랜드의 최근 생성 이력. 히스토리 탭용."""
        stmt = (
            select(Generation)
            .where(Generation.brand_id == brand_id)
            .options(selectinload(Generation.outputs))
            .order_by(Generation.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_products(self, brand_id: UUID) -> list[ProductGroup]:
        """같은 product_name 을 하나의 상품군으로 묶어 대표 Generation 정보 반환.

        드롭다운용. 각 상품군의 **가장 최근** Generation 을 대표로 사용.
        """
        # 모든 Generation 을 최신순으로 읽어 파이썬에서 product_name 별 첫 번째만 취함.
        # 동일 timestamp 에서 FK 매칭이 애매해지는 문제를 피하고 구현을 단순화.
        stmt = (
            select(Generation)
            .where(Generation.brand_id == brand_id)
            .order_by(Generation.created_at.desc(), Generation.id.desc())
        )
        result = await self.session.execute(stmt)
        rows = list(result.scalars().all())

        counts: dict[str, int] = {}
        for gen in rows:
            counts[gen.product_name] = counts.get(gen.product_name, 0) + 1

        seen: set[str] = set()
        groups: list[ProductGroup] = []
        for gen in rows:
            if gen.product_name in seen:
                continue
            seen.add(gen.product_name)
            groups.append(
                ProductGroup(
                    product_name=gen.product_name,
                    product_description=gen.product_description,
                    product_image_path=gen.product_image_path,
                    latest_generation_id=gen.id,
                    generation_count=counts[gen.product_name],
                )
            )
        return groups
