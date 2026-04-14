# 데이터 스키마 — 개선안 (미래 후보)

현재 확정안은 [schema.md](schema.md). 본 문서는 지금 당장 적용하진 않지만 **조건이 충족되면 재검토할 리팩터 후보**를 기록한다.

---

## 1. `reference_images` 광역 재사용

**현재**: `reference_images.brand_id` FK — 브랜드 소유로 격리.

**개선 시나리오**:
- "프랜차이즈 공통 레퍼런스 갤러리" 니즈가 생기면 소유 레벨을 올림 (예: `org_id`).
- 공개 레퍼런스 풀을 제공할 경우 `is_public` 플래그 추가.

**도입 시점**: 조직 단위 사용자 확보 후.

---

## 2. 스타일 재분석 허용

**현재 제약**: 온보딩 후 `brands` 수정 불가 (원칙 #4).

**개선 시나리오**: 계절·리브랜딩 등으로 스타일 재생성 니즈가 생기면 `brands` 에서 스타일 섹션을 분리해 `style_profiles` 별도 테이블로 이관 + 버전 관리.

```
BRANDS (아이덴티티만 유지)
  └──< STYLE_PROFILES (버전 append-only)
          ├── is_current 플래그
          ├── analyzer_prompt_version
          └── GENERATIONS.style_profile_id FK 추가
```

**도입 시점**: 사용자 피드백에서 "스타일 다시 뽑고 싶다" 가 누적될 때.

---

## 3. Alembic 도입 시점

**현재**: `Base.metadata.create_all` 로 부트스트랩. 단일 로컬 DB.

**개선 트리거**:
- staging ↔ production 환경 분리 필요
- 이미 운영 중인 DB 에 스키마 변경이 필요 (데이터 유실 불가)
- 팀원 간 DB 스키마 동기화 문제 발생

**도입 방법**:
1. 현재 스키마를 **baseline revision** 으로 stamp (`alembic stamp head`)
2. 이후 변경부터 `alembic revision --autogenerate` 로 추적
3. `alembic.ini` 의 `sqlalchemy.url` 은 환경별로 주입

---

## 4. 비용/토큰 기록

**현재**: Langfuse 에서 자동 계산.

**개선 시나리오**:
- Langfuse 장애·요금 이슈로 DB 이중화가 필요해질 경우 `generations.tokens_input` / `tokens_output` / `cost_usd` 컬럼 추가.
- 현 시점엔 불필요. Langfuse trace 조회로 충분.

---

## 5. 프롬프트 템플릿 독립 테이블

**현재**: 시스템 프롬프트 버전은 Langfuse prompt 관리 기능 사용.

**개선 시나리오**: Langfuse 의존 없이 DB 에 버저닝을 두고 싶으면 `prompt_templates(id, name, version, content, created_at)` 신설. `generations.analyzer_prompt_version` 이 부활하며 FK 로 연결.

**도입 시점**: 프롬프트 A/B 테스트를 DB 쿼리 기반으로 분석하고 싶을 때.

---

## 6. 참조 이미지 단발성 저장

**현재**: `reference_images` 를 재사용 단위로 분리.

**개선 시나리오**: 실제 사용 데이터에서 참조 이미지 재사용률이 현저히 낮으면 별도 테이블을 없애고 `generations.composition_prompt` 컬럼 하나로 통합. 테이블 축소.

**판정 기준**: 생성 요청 중 "기존 reference_image_id 를 고른" 비율 < 10% 가 3개월 이상 지속.

---

## 7. `generation_outputs.index` / `revised_prompt` 복원

**현재**: 둘 다 제거 (필요성 낮음).

**재도입 조건**:
- `index`: 동일 kind(예: `ad_copy`) 산출물의 **순서가 UI 표시에 의미를 갖는 시점**.
- `revised_prompt`: 이미지 생성 모델이 프롬프트를 revise 한 내용을 **DB 내에서 바로 보고 싶을 때** (현재는 Langfuse 조회).

---

## 참고

- 본 문서는 "언제가 될지 모르는 미래 후보" 모음. 실제로 적용할 때는 별도 설계 리뷰와 함께 [schema.md](schema.md) 로 반영.
- 삭제 후보로 올렸다가 필요해져서 복원하는 케이스도 모두 본 문서에 흔적을 남긴다.
