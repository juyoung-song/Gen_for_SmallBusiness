# Instagram OAuth — won/final 이식 메모

> Legacy note: 이 문서는 과거 `refactor/won/final` 이식 당시의 결정 기록이다.
> 현재 모바일 PWA 기준 구현은 `BrandImage`/`brand_config_id`가 아니라 `Brand`/`brand_id`/`brands.instagram_account_id` 기준이다.
> 또한 모바일 업로드는 `.env`의 `META_ACCESS_TOKEN` fallback을 사용하지 않고, 사용자가 OAuth로 직접 연결한 계정만 사용한다.
> 현재 팀원 셋업은 [instagram_team_onboarding_guide.md](instagram_team_onboarding_guide.md)를 우선한다.

> 이 문서는 `refactor/won/final` 브랜치에서 `refactor/song/main-fix-insta` 의
> Instagram OAuth 기능을 이식할 때의 **won 고유 결정 사항** 과 **미래 마이그레이션
> 경로** 를 남기는 메모다. 본격 설계는 `instagram_oauth_implementation_plan.md`
> (song 작성본) 를, 팀원 셋업 가이드는 `instagram_team_onboarding_guide.md`
> 를 참고한다.

---

## 1. 배경 — song 과 won 의 구조 차이

song 브랜치는 온보딩된 브랜드 정보를 `BrandConfig` 라는 별도 모델로 관리한다.
won 브랜치는 동일한 역할을 `BrandImage` 모델이 담당한다 ([models/brand_image.py](../models/brand_image.py)).

song 의 OAuth 코드는 **`brand_config.id: UUID`** 를 `instagram_connections.brand_config_id`
컬럼에 그대로 저장하는 방식을 전제로 작성됐다. 즉 다음 두 가지가 암묵적으로 전제된다.

1. `brand_config` 객체에 `.id: UUID` 속성이 있을 것
2. 그 `.id` 값이 **"사용자(또는 브랜드)" 의 stable identifier** 일 것

## 2. won 이 채택한 방식 — 옵션 1: duck typing + 고아 row 허용

이식 당시 사용자 결정 (2026-04-10):

> **"옵션 1 가되, 문서로 옵션 2 살려두자."**

### 구현 요약
- won 의 `BrandImage` 인스턴스를 그대로 `brand_config` 인자로 넘긴다.
- `BrandImage.id` 가 `UUID` 이므로 song 의 `brand_config.id` 전제와 호환된다.
- song 의 파일들은 **수정 없이 그대로** 사용.
- [services/instagram_auth_adapter.py](../services/instagram_auth_adapter.py) 와
  [ui/instagram_connect.py](../ui/instagram_connect.py) 는 `brand_config.id`
  만 참조하므로 런타임에 `BrandImage` 인지 `BrandConfig` 인지 구분하지 못하고,
  또 구분할 필요도 없다.

### 장점
- 이식 작업이 수 분. song 파일 수정 0줄.
- song 저자의 롤백 설계 (`services/instagram_auth_adapter.py` 한 파일만 지우면 기존
  `.env` 기반 업로드 경로 복구) 가 그대로 유효.

### 단점 — "고아 row" 시나리오

`BrandImage` 는 재온보딩 시 **새 row 가 생성** 되며 `id: UUID` 가 바뀐다
(won 의 현재 온보딩 정책). 다음 시나리오가 발생할 수 있다.

```
[Day 1] user_id="default" 온보딩
        → BrandImage(id=UUID-A) 생성
        → 사용자가 인스타 OAuth 연동
        → instagram_connections(brand_config_id=UUID-A) 저장

[Day 7] user_id="default" 가 재온보딩 (테스트 / 정책 변경 / 사용자 요청 등)
        → BrandImage(id=UUID-B) 생성 (NEW id)
        → 앱이 BrandImage(UUID-B) 를 brand_config 로 넘김
        → get_connection(UUID-B) → None
        → 사용자 입장: "어? 인스타 다시 연결하라고 하네"
        → DB: instagram_connections(UUID-A) row 는 고아로 남는다
          (암호화된 토큰 + IG 계정 정보가 DB 에 계속 존재)
```

### 고아 row 허용의 근거
1. MVP 단계 — 사장님 사용 흐름에서 재온보딩이 빈번하지 않다.
2. 재연결은 사이드바 버튼 한 번. 사용자 부담 낮음.
3. 암호화된 토큰은 `token_expires_at` 이 지나면 Meta 에서도 무효화된다.
4. 필요 시 옵션 2 로 언제든 마이그레이션 가능 (아래 §3 참고).

---

## 3. 미래 옵션 2 — brand_config_id → user_id 로 전환

MVP 가 성장해서 재온보딩이 일상화되거나, 다중 사용자 지원이 필요해지거나,
고아 row 누적이 문제가 되면 이 경로로 마이그레이션한다.

### 3.1 목표

`instagram_connections` 의 외래 키를 **재온보딩 시 바뀌지 않는 stable identifier**
로 교체한다. 현재 won 은 단일 사용자이므로 `user_id: str`
(예: `"default"`) 가 그 역할을 한다. 다중 사용자가 도입되면 별도 `users`
테이블의 `user_id` 가 된다.

### 3.2 변경해야 할 파일 (추정)

| 파일 | 변경 내용 |
|---|---|
| [models/instagram_connection.py](../models/instagram_connection.py) | `brand_config_id: UUID unique` → `user_id: str(64) unique` 로 컬럼 교체 |
| [services/instagram_auth_service.py](../services/instagram_auth_service.py) | `save_connection` / `get_connection` / `revoke_connection` 시그니처의 `brand_config_id: UUID` → `user_id: str`. 내부 WHERE 절도 변경 |
| [services/instagram_auth_adapter.py](../services/instagram_auth_adapter.py) | `apply_user_token(settings, brand_config)` 의 내부 `brand_config.id` 참조를 `"default"` (또는 현재 세션의 user_id) 로 변경. 또는 시그니처를 `apply_user_token(settings, user_id: str)` 로 변경 |
| [ui/instagram_connect.py](../ui/instagram_connect.py) | `render_instagram_connection(settings, brand_config)` 의 `brand_config.id` 참조를 `user_id` 로 변경. brand_config 가 None 여부 체크는 "온보딩 완료 여부" 로 의미만 이어받음 |
| [app.py](../app.py) | `render_instagram_connection` 및 `apply_user_token` 호출 사이트에 `user_id` 전달 |

### 3.3 DB 마이그레이션

현재 won 은 Alembic 없이 `init_db()` + `create_all()` 로 스키마를 만든다. 옵션 2 로 가려면:

- **쉬운 경로**: 개발 중이므로 `data/history.db` 삭제 → `init_db()` 재생성. 이 경우 기존
  OAuth 연결 정보 날아감. 사용자가 다시 연동.
- **제대로 된 경로**: Alembic 도입 + 마이그레이션 스크립트 작성
  - `ALTER TABLE instagram_connections ADD COLUMN user_id VARCHAR(64)`
  - 기존 `brand_config_id` 를 `BrandImage.user_id` 로 조인해서 채움
  - `brand_config_id` 컬럼 DROP
  - `user_id` 에 UNIQUE 추가

### 3.4 앱 호출부 변경 예시

#### 현재 (옵션 1 — 덕타이핑)

```python
# app.py
brand_image = run_async(brand_image_service.get_for_user("default"))
render_instagram_connection(settings, brand_config=brand_image)

# 업로드 직전
apply_user_token(settings, brand_config=brand_image)
```

#### 미래 (옵션 2 — user_id 기반)

```python
# app.py
user_id = "default"  # 또는 현재 세션 user
render_instagram_connection(settings, user_id=user_id)

# 업로드 직전
apply_user_token(settings, user_id=user_id)
```

---

## 4. 함께 남겨둘 결정 사항

- **`.env` fallback 유지**: `META_ACCESS_TOKEN` / `INSTAGRAM_ACCOUNT_ID` 가 `.env` 에
  남아있으면 OAuth 연결이 없어도 업로드가 동작한다
  ([services/instagram_auth_adapter.py](../services/instagram_auth_adapter.py) L42-43).
  MVP 단계에서 기존 테스트/개발 환경이 깨지지 않도록 유지.
- **사이드바 배치**: `render_sidebar_settings(settings)` 아래. 온보딩 완료 이후에만
  ([app.py](../app.py) 의 `onboarded == True` 분기 안).
- **Meta 앱 개발 모드**: Meta 개발자 센터의 앱이 현재 "개발 모드" 라서 테스터로 등록되지
  않은 팀원은 OAuth 로그인 자체가 차단된다. 신규 팀원 합류 시
  [instagram_team_onboarding_guide.md](instagram_team_onboarding_guide.md) §1 의
  테스터 초대 절차를 반드시 거친다.
- **redirect URI 슬래시**: `META_REDIRECT_URI=http://localhost:8501/` (끝 슬래시 필수).
  Meta 는 엄격하게 매칭한다.

---

## 5. 추적용 레퍼런스

- song 원본 설계: [instagram_oauth_implementation_plan.md](instagram_oauth_implementation_plan.md)
- 팀원 셋업 가이드: [instagram_team_onboarding_guide.md](instagram_team_onboarding_guide.md)
- song 이식 커밋(이 브랜치에서): _커밋 후 SHA 채워 넣기_
- song 측 원본 feature 커밋: `8da2bb5 feat(instagram): OAuth 2.0 자동 연동 및 수동 연동 fallback 구현`
