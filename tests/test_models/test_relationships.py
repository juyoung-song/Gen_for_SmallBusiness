"""모델 relationship / cascade 동작 검증.

docs/schema.md 기준:
- Brand 삭제 시 reference_images / generations 는 cascade 로 함께 삭제
- Generation 삭제 시 generation_outputs 함께
- GenerationOutput 삭제 시 generated_uploads 함께
"""

"""FK ON DELETE CASCADE 검증 — raw DELETE 로 DB 레벨 동작만 확인.

ORM 의 `cascade="all, delete-orphan"` 은 파이썬 레벨에서 자식 컬렉션을 로드한 뒤
삭제하는 방식이라 async 세션에서 깊은 체인을 다루기 까다롭다. 실제 운영 환경에서
중요한 것은 `ondelete="CASCADE"` 가 붙은 FK 가 DB 에서 제대로 작동하느냐이므로,
여기서는 SQL DELETE 를 직접 실행해 FK cascade 동작만 검증한다.
"""

from sqlalchemy import delete, select

from models.brand import Brand
from models.generated_upload import GeneratedUpload
from models.generation import Generation
from models.generation_output import GenerationOutput
from services.generation_service import GenerationService, OutputSpec
from services.upload_service import UploadService


async def _count(session, model) -> int:
    result = await session.execute(select(model))
    return len(list(result.scalars().all()))


class TestBrandCascade:
    async def test_delete_brand_removes_generations_and_uploads(
        self, db_session, brand_factory
    ):
        brand = await brand_factory()
        gen = await GenerationService(db_session).create_with_outputs(
            brand_id=brand.id, reference_image_id=None,
            product_name="p", product_description="d", product_image_path=None,
            goal="g", tone="기본", is_new_product=False,
            outputs=[OutputSpec(kind="image", content_path="/tmp/x.png")],
        )
        image_out = next(o for o in gen.outputs if o.kind == "image")
        await UploadService(db_session).create(
            generation_output_id=image_out.id, kind="feed", caption="c",
        )

        # 생성 직후 상태 확인
        assert await _count(db_session, Generation) == 1
        assert await _count(db_session, GenerationOutput) == 1
        assert await _count(db_session, GeneratedUpload) == 1

        # raw DELETE (FK ON DELETE CASCADE 가 자식 레코드를 지워야 함)
        await db_session.execute(delete(Brand).where(Brand.id == brand.id))
        await db_session.commit()

        assert await _count(db_session, Generation) == 0
        assert await _count(db_session, GenerationOutput) == 0
        assert await _count(db_session, GeneratedUpload) == 0


class TestGenerationCascade:
    async def test_delete_generation_removes_outputs_and_uploads(
        self, db_session, brand_factory
    ):
        brand = await brand_factory()
        gen = await GenerationService(db_session).create_with_outputs(
            brand_id=brand.id, reference_image_id=None,
            product_name="p", product_description="d", product_image_path=None,
            goal="g", tone="기본", is_new_product=False,
            outputs=[
                OutputSpec(kind="image", content_path="/tmp/x.png"),
                OutputSpec(kind="ad_copy", content_text="c"),
            ],
        )
        image_out = next(o for o in gen.outputs if o.kind == "image")
        await UploadService(db_session).create(
            generation_output_id=image_out.id, kind="feed", caption="c",
        )

        await db_session.execute(delete(Generation).where(Generation.id == gen.id))
        await db_session.commit()

        assert await _count(db_session, GenerationOutput) == 0
        assert await _count(db_session, GeneratedUpload) == 0
