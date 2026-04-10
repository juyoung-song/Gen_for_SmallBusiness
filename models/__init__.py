"""ORM 모델 패키지.

신규 모델 추가 시:
1. 새 파일을 `models/<name>.py` 에 작성
2. 본 파일에 import + __all__ 등재
3. `tests/conftest.py` 의 import 블록에도 한 줄 추가 (Base.metadata 등록을 위해)
4. `config/database.py` `init_db()` 에도 동일하게 import 추가
"""

from models.base import Base, TimestampMixin
from models.brand_image import BrandImage
from models.generated_upload import GeneratedUpload
from models.instagram_connection import InstagramConnection
from models.product import Product

__all__ = [
    "Base",
    "TimestampMixin",
    "BrandImage",
    "Product",
    "GeneratedUpload",
    "InstagramConnection",
]
