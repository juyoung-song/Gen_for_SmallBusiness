# Instagram OAuth 계정 연결 — 종합 구현 설계서

> Legacy note: 이 문서는 Streamlit `app.py` 기반 OAuth 구현 설계서다.
> 현재 모바일 PWA 구현은 `mobile_app.py`의 `/api/mobile/instagram/*` 엔드포인트와 Stitch UI를 기준으로 한다.
> 모바일 업로드는 OAuth 연결 계정만 사용하며 `.env`의 `META_ACCESS_TOKEN` fallback을 사용하지 않는다.
> 현재 팀원 셋업은 [instagram_team_onboarding_guide.md](instagram_team_onboarding_guide.md)를 우선한다.

> **목적**: 사용자가 개발자 콘솔에 접근하지 않고, 서비스 내 "인스타그램 연결" 버튼 하나로 자신의 계정을 연동하여 광고를 자동 게시할 수 있게 한다.
>
> **절대 원칙**: 기존 서비스의 생성·업로드·UI 흐름은 일체 변경하지 않는다.

---

## 1. 기능 목표 정의

### 1.1 목적
현재 `.env`에 하드코딩된 `META_ACCESS_TOKEN`과 `INSTAGRAM_ACCOUNT_ID`를 **사용자별로 자동 취득**하여, 각 사장님의 인스타그램 계정에 광고를 게시할 수 있도록 한다.

### 1.2 사용자 입장에서 달라지는 점

| AS-IS (현재) | TO-BE (목표) |
|---|---|
| 개발자가 `.env`에 토큰을 직접 입력 | 사장님이 "인스타그램 연결" 버튼 클릭 → Facebook 로그인 → 자동 완료 |
| 단일 계정만 지원 | 사장님마다 자기 계정으로 게시 가능 |
| 토큰 만료 시 수동 갱신 필요 | 60일 장기 토큰 자동 발급 + 만료 경고 |

### 1.3 기존 흐름에서의 위치
```
[온보딩] → [상품 입력] → [생성] → [미리보기] → [인스타 업로드]
                                                     ↑
                                          여기에 "계정 연결 여부" 체크 삽입
                                          (미연결 시 연결 유도, 연결 시 기존 로직 그대로)
```
- **삽입 지점 1**: 사이드바에 "📷 인스타그램 연결" 섹션 추가
- **삽입 지점 2**: 업로드 버튼 클릭 시점에 연결 상태 분기

### 1.4 왜 "토큰 발급"이 아니라 "계정 연결"인가
- **사용자 관점**: "토큰"은 개발 용어이며 사장님에겐 의미 없음
- **UX 관점**: "내 인스타그램 계정 연결하기" = 직관적이고 신뢰감을 줌
- **기술 관점**: 내부적으로는 OAuth 토큰 발급이지만, 사용자에겐 "연결/해제" 개념으로 추상화

---

## 2. 기존 서비스 영향 최소화 원칙

### 2.1 절대 수정 금지 영역

| 파일/모듈 | 이유 |
|---|---|
| `services/text_service.py` | 광고 문구 생성 핵심 로직 |
| `services/image_service.py` | 이미지 생성 핵심 로직 |
| `services/analysis_service.py` | 브랜드 분석 핵심 로직 |
| `services/instagram_service.py` | 기존 업로드 핵심 로직 |
| `utils/prompt_builder.py` | 프롬프트 엔진 |
| `models/history.py`, `models/brand.py`, `models/product.py` | 기존 데이터 모델 |
| `schemas/` 전체 | 기존 스키마 |

### 2.2 최소 수정 허용 영역

| 파일 | 수정 범위 | 이유 |
|---|---|---|
| `app.py` | 사이드바에 연결 UI 호출 삽입 (~5줄) | 연결 상태 표시 |
| `app.py` | 업로드 버튼 직전에 연결 여부 분기 (~3줄×2) | 미연결 안내 |
| `config/settings.py` | OAuth 환경변수 4개 추가 | META_APP_ID 등 |
| `config/database.py` | import 1줄 추가 | 새 테이블 자동 생성 |
| `.env` | 환경변수 4줄 추가 | OAuth 필수값 |

### 2.3 구조적 접근: **어댑터 패턴(Adapter Pattern)**

```
기존 InstagramService (수정 안 함)
    ↑ settings.META_ACCESS_TOKEN 으로 토큰 참조
    ↑
[InstagramAuthAdapter] ← 새로 만드는 어댑터
    │ DB에서 사용자별 토큰을 꺼내서
    │ settings 객체에 동적으로 주입
    ↓
app.py 업로드 시점에서 어댑터 호출
```

**왜 어댑터인가?**
- 기존 `InstagramService`는 `self.settings.META_ACCESS_TOKEN`만 바라봄
- 어댑터가 DB에서 토큰을 꺼내 settings에 주입하면, 기존 서비스 코드 수정 없이 사용자별 토큰 자동 적용
- 롤백 시 어댑터만 제거하면 원복 완료

---

## 3. UX 흐름 설계

### 3.1 인스타그램 연결 UI 위치 (사이드바)

```
┌──────────────────────────────────┐
│  사이드바 (sidebar)               │
│  ┌────────────────────────────┐  │
│  │ 📷 인스타그램 계정          │  │
│  │                            │  │
│  │ ● 연결 안 됨               │  │  ← 미연결 상태
│  │ [🔗 인스타그램 연결하기]    │  │
│  │                            │  │
│  │ ✅ @bakerycafe 연결됨      │  │  ← 연결 상태
│  │ [🔄 다시 연결] [❌ 해제]    │  │
│  └────────────────────────────┘  │
└──────────────────────────────────┘
```

### 3.2 상태별 사용자 경험

#### 미연결 상태
- 광고 생성은 **정상 허용** (생성 기능은 인스타와 무관)
- 업로드 버튼 클릭 시:
```
⚠️ 인스타그램 계정이 연결되어 있지 않습니다.
왼쪽 사이드바에서 [인스타그램 연결하기] 버튼을 눌러 계정을 연결해주세요.
연결 후 다시 이 버튼을 누르면 바로 올라갑니다!
```

#### 연결 완료 상태
- 기존과 100% 동일한 업로드 흐름 (어댑터가 토큰을 주입하므로)
- 사이드바에 연결된 계정 이름 표시

### 3.3 연결 과정 (사장님 시점)

```
1. 사이드바에서 [🔗 인스타그램 연결하기] 클릭
2. 새 브라우저 탭이 열림 → Facebook 로그인 화면
3. 로그인 → "이 앱이 인스타그램에 게시할 권한을 요청합니다" → [허용]
4. 자동으로 원래 서비스 페이지로 돌아옴
5. 사이드바에 "✅ @my_cafe_official 연결됨" 표시
```

### 3.4 실제 문구 예시

| 상황 | 문구 |
|---|---|
| 사이드바 미연결 | `📷 인스타그램 계정이 아직 연결되지 않았어요` |
| 연결 버튼 | `🔗 내 인스타그램 연결하기` |
| 연결 성공 | `✅ @{username} 계정이 연결되었습니다!` |
| 업로드 시 미연결 | `⚠️ 인스타그램 계정을 먼저 연결해주세요!` |
| 토큰 만료 임박 | `⏰ 인스타그램 연결이 곧 만료됩니다. [다시 연결하기]를 눌러주세요.` |
| 연결 실패 | `❌ 연결에 실패했습니다. 인스타그램이 비즈니스 또는 크리에이터 계정인지 확인해주세요.` |

---

## 4. 백엔드 아키텍처 설계

### 4.1 OAuth 처리 방식: Streamlit query_params (추가 서버 불필요)

```
[연결 버튼 클릭]
  → 브라우저를 Meta OAuth URL로 리다이렉트
  → 사용자 로그인/동의
  → Meta가 redirect_uri (= Streamlit 앱 URL + ?code=xxx&state=yyy) 로 콜백
  → Streamlit이 query_params에서 code 추출
  → 백엔드 서비스가 code → access_token → long-lived token 변환
  → DB 저장
```

### 4.2 OAuth 처리 흐름 (상세)

```
Step 1: "연결하기" 클릭
  → state = UUID 생성 + session_state에 저장
  → redirect URL 조립:
    https://www.facebook.com/v19.0/dialog/oauth
      ?client_id={META_APP_ID}
      &redirect_uri={META_REDIRECT_URI}
      &state={state}
      &scope=instagram_basic,instagram_content_publish,
             pages_show_list,pages_read_engagement

Step 2: Meta 콜백 (Streamlit URL로 돌아옴)
  → st.query_params에서 code, state 추출
  → state 검증

Step 3: code → Short-lived Token
  POST https://graph.facebook.com/v19.0/oauth/access_token

Step 4: Short-lived → Long-lived Token (60일)
  GET https://graph.facebook.com/v19.0/oauth/access_token
    ?grant_type=fb_exchange_token

Step 5: Instagram Business Account ID 자동 조회
  GET https://graph.facebook.com/v19.0/me/accounts
  → 각 Page에서 instagram_business_account.id 추출

Step 6: DB 저장 + session_state 갱신
```

### 4.3 세션 기반 사용자 식별

회원가입이 없으므로 **brand_config의 id**(UUID)를 사용자 식별자로 활용합니다.

```python
# 온보딩 완료 시 brand_config.id가 생성됨
# 이 ID를 instagram_connections 테이블의 FK로 사용
# → 1 brand_config : 1 instagram_connection
```

**추후 회원가입 도입 시 확장:**
- `user_id` 컬럼을 `instagram_connections`에 추가
- `brand_config`에도 `user_id` FK 추가
- 기존 `brand_config.id` 기반 연결은 마이그레이션으로 `user_id`에 매핑

---

## 5. 데이터 모델 설계

### 5.1 신규 테이블: `instagram_connections`

```python
# models/instagram_connection.py (신규 파일)

class InstagramConnection(Base, TimestampMixin):
    __tablename__ = "instagram_connections"

    id: Mapped[UUID]                     # PK
    brand_config_id: Mapped[UUID]        # FK (unique, 1:1)
    access_token: Mapped[str]            # 암호화 저장 (Fernet)
    token_type: Mapped[str]              # "short_lived" | "long_lived"
    token_expires_at: Mapped[datetime]   # 만료 시각
    instagram_account_id: Mapped[str]    # IG 비즈니스 계정 ID
    instagram_username: Mapped[str]      # @username (UI 표시용)
    facebook_page_id: Mapped[str]        # 연결된 FB 페이지 ID
    facebook_page_name: Mapped[str]      # FB 페이지 이름
    is_active: Mapped[bool]              # 연결 상태 (soft delete)
```

### 5.2 필드별 저장 전략

| 필드 | 예시 값 | 암호화 여부 |
|---|---|---|
| `access_token` | `EAAKJ41cVQfc...` | ✅ 필수 (Fernet) |
| `instagram_account_id` | `17841440691546363` | ❌ 공개 정보 |
| `instagram_username` | `@bakerycafe` | ❌ UI 표시용 |
| `token_expires_at` | `2026-06-08T00:00:00Z` | ❌ 만료 체크용 |

### 5.3 기존 테이블 영향: **없음**

---

## 6. 구현 단계별 개발 계획

### Phase 1: 기반 구축 (Day 1)
- [ ] `models/instagram_connection.py` 생성
- [ ] `config/database.py`에 import 1줄 추가
- [ ] `config/settings.py`에 환경변수 4개 추가
- [ ] `.env`에 해당 값 추가

### Phase 2: OAuth 서비스 구현 (Day 1~2)
- [ ] `services/instagram_auth_service.py` 생성
- [ ] `utils/crypto.py` 생성

### Phase 3: 어댑터 구현 (Day 2)
- [ ] `services/instagram_auth_adapter.py` 생성

### Phase 4: UI 통합 (Day 2~3)
- [ ] `ui/instagram_connect.py` 생성
- [ ] `app.py` 사이드바에 호출 삽입 (~5줄)
- [ ] `app.py` 업로드 버튼에 연결 체크 삽입 (~3줄×2)

### Phase 5: 예외 처리 (Day 3)
- [ ] 토큰 만료 감지 + 사이드바 경고
- [ ] 개인 계정/권한 거부/업로드 실패 안내

### Phase 6: 테스트 (Day 3~4)
- [ ] Mock 모드 시뮬레이션
- [ ] 실제 Meta 테스트 앱 E2E 검증

---

## 7. 기존 코드베이스 반영 가이드

### 7.1 파일 구조 (신규 파일 ★ 표시)

```
3차 프로젝트_final/
├── app.py                              # 최소 수정 (~11줄)
├── config/
│   ├── settings.py                     # 최소 수정 (+4줄)
│   └── database.py                     # 최소 수정 (+1줄)
├── models/
│   ├── instagram_connection.py         # ★ 신규
│   └── (기존 파일 수정 없음)
├── schemas/
│   └── instagram_schema.py             # ★ 신규
├── services/
│   ├── instagram_auth_service.py       # ★ 신규
│   ├── instagram_auth_adapter.py       # ★ 신규
│   ├── instagram_service.py            # 수정 없음
│   └── (기존 파일 수정 없음)
├── ui/
│   └── instagram_connect.py            # ★ 신규
└── utils/
    └── crypto.py                       # ★ 신규
```

### 7.2 환경변수 추가 (`.env`)

```env
# ── Instagram OAuth App Settings ──
META_APP_ID=123456789012345
META_APP_SECRET=abcdef1234567890abcdef1234567890
META_REDIRECT_URI=http://localhost:8501
TOKEN_ENCRYPTION_KEY=your-fernet-key-here
```

### 7.3 `config/settings.py` 최소 수정

```python
# 기존 Instagram Upload Settings 블록 아래에 추가
# ── Instagram OAuth App Settings ──
META_APP_ID: str = ""
META_APP_SECRET: str = ""
META_REDIRECT_URI: str = "http://localhost:8501"
TOKEN_ENCRYPTION_KEY: str = ""
```

### 7.4 `config/database.py` 최소 수정

```python
# 기존 import 블록(라인 36)에 1줄 추가
import models.instagram_connection
```

### 7.5 `app.py` 최소 수정 — 사이드바 (라인 125 부근)

```python
# render_sidebar_settings(settings) 직후에 삽입
from ui.instagram_connect import render_instagram_connection
ig_connection = render_instagram_connection(settings, brand_config)
```

### 7.6 `app.py` 최소 수정 — 업로드 분기 (라인 257 부근)

```python
# 기존 업로드 버튼 코드 앞에 3줄 삽입
if st.button("🚀 내 인스타그램에 바로 올리기", ...):
    from services.instagram_auth_adapter import apply_user_token
    if not apply_user_token(settings, brand_config):
        st.warning("⚠️ 인스타그램 계정을 먼저 연결해주세요!")
    else:
        # 기존 업로드 코드 그대로
        from services.instagram_service import InstagramService
        ig_svc = InstagramService(settings)
        ...
```

---

## 8. 예외 처리 및 운영 이슈

| 시나리오 | 사용자 메시지 | 기술 처리 |
|---|---|---|
| **개인 계정 연결 시도** | `"비즈니스 또는 크리에이터 계정만 연결 가능합니다."` | `ig_business_account` 필드 없으면 감지 |
| **권한 동의 취소** | `"연결이 취소되었습니다."` | query_params에 `error=access_denied` 감지 |
| **토큰 만료 (60일)** | `"⏰ 연결이 만료되었습니다. 다시 연결해주세요."` | `token_expires_at` 체크, 7일 전 경고 |
| **업로드 실패** | `"잠시 후 다시 시도해주세요."` | 기존 에러 핸들링 유지 |
| **FB 페이지 없음** | `"Facebook 페이지에 연결되어 있어야 합니다."` | `/me/accounts` 빈 배열 감지 |
| **연결됐는데 게시 안 됨** | `"게시 권한 부족. 다시 연결해주세요."` | 401/403 시 `is_active=False` |

---

## 9. 보안 설계

### 9.1 토큰 저장: Fernet 대칭 암호화

```python
# utils/crypto.py
from cryptography.fernet import Fernet

def encrypt_token(token: str, key: str) -> str:
    f = Fernet(key.encode())
    return f.encrypt(token.encode()).decode()

def decrypt_token(encrypted: str, key: str) -> str:
    f = Fernet(key.encode())
    return f.decrypt(encrypted.encode()).decode()
```

### 9.2 절대 노출 금지 값

| 값 | 저장 위치 | 노출 |
|---|---|---|
| `META_APP_SECRET` | `.env` 서버 | ❌ 절대 금지 |
| `access_token` | DB 암호화 | ❌ 절대 금지 |
| `TOKEN_ENCRYPTION_KEY` | `.env` 서버 | ❌ 절대 금지 |
| `META_APP_ID` | OAuth URL | ⚠️ 정상 (공개 값) |
| `instagram_username` | DB | ✅ UI 표시 |

### 9.3 보안 체크리스트

- [ ] `META_APP_SECRET` 코드 하드코딩 금지
- [ ] access_token DB 암호화 저장 (Fernet)
- [ ] OAuth state 파라미터 CSRF 방지
- [ ] HTTPS 환경에서만 OAuth (프로덕션)
- [ ] `.env`는 `.gitignore`에 포함 ✅

---

## 10. MVP 범위와 확장 범위

### MVP (지금 구현)

| 기능 | 이유 |
|---|---|
| OAuth 연결/해제 | 핵심 — 없으면 서비스 확장 불가 |
| 장기 토큰 자동 발급 | 사용자 편의 핵심 |
| 사이드바 연결 상태 표시 | 최소 UX |
| 업로드 시 연결 체크 | 에러 방지 |
| 토큰 암호화 저장 | 보안 기본 |

### 확장 (나중에)

| 기능 | 이유 |
|---|---|
| 토큰 자동 갱신 (refresh) | 재연결 유도로 MVP 충분 |
| 다중 계정 | 현재 1 브랜드 = 1 계정 |
| 회원가입 통합 | 현재 회원 시스템 없음 |
| 게시 예약 | 별도 기능 |

---

## 11. 코드 수정 전략

### 11.1 기존 파일 수정 목록 (최소)

| 파일 | 수정 라인 수 | 내용 |
|---|---|---|
| `config/settings.py` | +4줄 | OAuth 환경변수 |
| `config/database.py` | +1줄 | import |
| `app.py` | +5줄 (사이드바) | render_instagram_connection() |
| `app.py` | +3줄×2 (업로드) | 연결 체크 분기 |
| `.env` | +4줄 | OAuth 값 |

### 11.2 신규 파일 목록

| 파일 | 역할 |
|---|---|
| `models/instagram_connection.py` | ORM 모델 |
| `schemas/instagram_schema.py` | Pydantic 스키마 |
| `services/instagram_auth_service.py` | OAuth 핵심 로직 |
| `services/instagram_auth_adapter.py` | 기존 서비스 연결 어댑터 |
| `ui/instagram_connect.py` | 사이드바 UI |
| `utils/crypto.py` | 토큰 암호화 |

### 11.3 롤백 전략

```
롤백 절차:
  1. 신규 파일 6개 삭제
  2. app.py 삽입한 ~11줄 삭제
  3. settings.py 추가한 4줄 삭제
  4. database.py 추가한 1줄 삭제

롤백 후:
  → 기존 .env 하드코딩 토큰으로 정상 동작 (원복)
  → instagram_connections 테이블은 DB에 남지만 무해
```

---

## 12. 바로 구현 가능한 TODO 리스트

### A. 구현 우선순위 체크리스트

```
[ ] 1. models/instagram_connection.py 생성
[ ] 2. schemas/instagram_schema.py 생성
[ ] 3. utils/crypto.py 생성
[ ] 4. services/instagram_auth_service.py 생성
[ ] 5. services/instagram_auth_adapter.py 생성
[ ] 6. ui/instagram_connect.py 생성
[ ] 7. config/settings.py에 환경변수 4개 추가
[ ] 8. config/database.py에 import 1줄 추가
[ ] 9. .env에 META_APP_ID, META_APP_SECRET 등 추가
[ ] 10. app.py 사이드바에 render_instagram_connection() 삽입
[ ] 11. app.py 피드 업로드 버튼에 연결 체크 분기 삽입
[ ] 12. app.py 스토리 업로드 버튼에 연결 체크 분기 삽입
[ ] 13. E2E 테스트 (Mock 모드)
[ ] 14. E2E 테스트 (실제 Meta 테스트 앱)
```

### B. Meta 개발자 센터 준비 항목

```
1. https://developers.facebook.com 에서 앱 생성
2. 앱 유형: "비즈니스" 선택
3. 제품 추가: "Facebook Login for Business" 활성화
4. OAuth 리다이렉트 URI 등록:
   - 개발: http://localhost:8501
   - 프로덕션: https://your-domain.com
5. 앱 ID, 앱 시크릿 복사 → .env에 입력
6. 권한 요청:
   - instagram_basic
   - instagram_content_publish
   - pages_show_list
   - pages_read_engagement
7. (프로덕션 배포 시) 앱 검수 제출
```

---

## 부록 B. 전체 사용자 흐름 시나리오

### Before (현재)

```
사장님이 앱을 처음 실행
  → 온보딩 (브랜드 정보 입력)
  → 상품 정보 입력
  → AI가 광고 글 + 사진 생성
  → "인스타에 올리기" 버튼 클릭
  → .env에 하드코딩된 토큰으로 업로드 (개발자 계정에만 올라감)
```

### After (목표)

```
사장님이 앱을 처음 실행
  → 온보딩 (브랜드 정보 입력) — 기존과 동일
  → 사이드바에 "📷 인스타그램 연결하기" 표시 — ★ 신규
    → 클릭 → Facebook 로그인 → 동의 → 자동 연결
    → "✅ @my_bakery 연결됨" 표시
  → 상품 정보 입력 — 기존과 동일
  → AI가 광고 글 + 사진 생성 — 기존과 동일
  → "인스타에 올리기" 버튼 클릭
    → (연결됨) → 사장님 계정에 자동 게시 — ★ 신규
    → (미연결) → "인스타를 연결해주세요!" 안내 — ★ 신규
  → 🎉 사장님 계정에 광고가 올라감!
```

---

## 부록 C. 핵심 코드 초안

### C.1 `services/instagram_auth_service.py` (핵심 클래스)

```python
"""Instagram OAuth 2.0 계정 연결 서비스."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID
import httpx
from config.settings import Settings
from config.database import AsyncSessionLocal
from models.instagram_connection import InstagramConnection
from utils.crypto import encrypt_token, decrypt_token
from sqlalchemy import select

logger = logging.getLogger(__name__)

class InstagramAuthService:
    GRAPH_API_VERSION = "v19.0"
    BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_oauth_url(self, state: str) -> str:
        return (
            f"https://www.facebook.com/{self.GRAPH_API_VERSION}/dialog/oauth"
            f"?client_id={self.settings.META_APP_ID}"
            f"&redirect_uri={self.settings.META_REDIRECT_URI}"
            f"&state={state}"
            f"&scope=instagram_basic,instagram_content_publish,"
            f"pages_show_list,pages_read_engagement"
        )

    async def exchange_code_for_token(self, code: str) -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.BASE_URL}/oauth/access_token", params={
                "client_id": self.settings.META_APP_ID,
                "redirect_uri": self.settings.META_REDIRECT_URI,
                "client_secret": self.settings.META_APP_SECRET,
                "code": code,
            })
            resp.raise_for_status()
            return resp.json()["access_token"]

    async def exchange_for_long_lived_token(self, short_token: str) -> tuple[str, int]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.BASE_URL}/oauth/access_token", params={
                "grant_type": "fb_exchange_token",
                "client_id": self.settings.META_APP_ID,
                "client_secret": self.settings.META_APP_SECRET,
                "fb_exchange_token": short_token,
            })
            resp.raise_for_status()
            data = resp.json()
            return data["access_token"], data.get("expires_in", 5184000)

    async def fetch_instagram_account(self, access_token: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.BASE_URL}/me/accounts",
                                    params={"access_token": access_token})
            resp.raise_for_status()
            pages = resp.json().get("data", [])
            if not pages:
                raise ValueError("Facebook 페이지가 없습니다.")

            page = pages[0]
            resp2 = await client.get(f"{self.BASE_URL}/{page['id']}",
                params={"fields": "instagram_business_account,name",
                        "access_token": access_token})
            resp2.raise_for_status()
            page_data = resp2.json()

            ig_account = page_data.get("instagram_business_account")
            if not ig_account:
                raise ValueError("Instagram 비즈니스 계정이 연결되어 있지 않습니다.")

            resp3 = await client.get(f"{self.BASE_URL}/{ig_account['id']}",
                params={"fields": "username", "access_token": access_token})
            resp3.raise_for_status()

            return {
                "instagram_account_id": ig_account["id"],
                "instagram_username": resp3.json().get("username", ""),
                "facebook_page_id": page["id"],
                "facebook_page_name": page_data.get("name", ""),
            }

    async def save_connection(self, brand_config_id: UUID,
                              access_token: str, expires_in: int,
                              ig_info: dict) -> InstagramConnection:
        encrypted = encrypt_token(access_token, self.settings.TOKEN_ENCRYPTION_KEY)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(InstagramConnection).where(
                    InstagramConnection.brand_config_id == brand_config_id))
            conn = result.scalar_one_or_none()

            if conn:
                conn.access_token = encrypted
                conn.token_expires_at = expires_at
                conn.instagram_account_id = ig_info["instagram_account_id"]
                conn.instagram_username = ig_info.get("instagram_username")
                conn.is_active = True
            else:
                conn = InstagramConnection(
                    brand_config_id=brand_config_id,
                    access_token=encrypted,
                    token_expires_at=expires_at,
                    instagram_account_id=ig_info["instagram_account_id"],
                    instagram_username=ig_info.get("instagram_username"),
                    facebook_page_id=ig_info.get("facebook_page_id"),
                    facebook_page_name=ig_info.get("facebook_page_name"),
                    is_active=True)
                session.add(conn)
            await session.commit()
            return conn

    async def get_connection(self, brand_config_id: UUID) -> Optional[InstagramConnection]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(InstagramConnection).where(
                    InstagramConnection.brand_config_id == brand_config_id,
                    InstagramConnection.is_active == True))
            return result.scalar_one_or_none()

    async def revoke_connection(self, brand_config_id: UUID) -> None:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(InstagramConnection).where(
                    InstagramConnection.brand_config_id == brand_config_id))
            conn = result.scalar_one_or_none()
            if conn:
                conn.is_active = False
                await session.commit()
```

### C.2 `services/instagram_auth_adapter.py`

```python
"""기존 InstagramService 어댑터 — settings에 사용자별 토큰 동적 주입."""
import logging
from config.settings import Settings
from utils.crypto import decrypt_token

logger = logging.getLogger(__name__)

def apply_user_token(settings: Settings, brand_config) -> bool:
    if not brand_config:
        return False
    import asyncio
    from services.instagram_auth_service import InstagramAuthService
    auth_svc = InstagramAuthService(settings)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()

    conn = loop.run_until_complete(auth_svc.get_connection(brand_config.id))

    if not conn or not conn.is_active:
        return bool(settings.META_ACCESS_TOKEN and settings.INSTAGRAM_ACCOUNT_ID)

    try:
        decrypted = decrypt_token(conn.access_token, settings.TOKEN_ENCRYPTION_KEY)
        settings.META_ACCESS_TOKEN = decrypted
        settings.INSTAGRAM_ACCOUNT_ID = conn.instagram_account_id
        return True
    except Exception as e:
        logger.error("토큰 복호화 실패: %s", e)
        return False
```

### C.3 `ui/instagram_connect.py`

```python
"""사이드바 인스타그램 계정 연결 UI 컴포넌트."""
import streamlit as st
from uuid import uuid4

def render_instagram_connection(settings, brand_config):
    if not brand_config:
        return None

    from services.instagram_auth_service import InstagramAuthService
    import asyncio
    auth_svc = InstagramAuthService(settings)

    def _run(coro):
        try:
            return asyncio.get_event_loop().run_until_complete(coro)
        except RuntimeError:
            return asyncio.run(coro)

    # OAuth 콜백 처리
    query_params = st.query_params
    if "code" in query_params and "state" in query_params:
        if query_params["state"] == st.session_state.get("oauth_state"):
            try:
                with st.spinner("인스타그램 계정 연결 중..."):
                    code = query_params["code"]
                    short_token = _run(auth_svc.exchange_code_for_token(code))
                    long_token, expires_in = _run(
                        auth_svc.exchange_for_long_lived_token(short_token))
                    ig_info = _run(auth_svc.fetch_instagram_account(long_token))
                    _run(auth_svc.save_connection(
                        brand_config.id, long_token, expires_in, ig_info))
                st.success(f"✅ @{ig_info['instagram_username']} 연결 완료!")
                st.query_params.clear()
                st.rerun()
            except Exception as e:
                st.error(f"❌ 연결 오류: {e}")
                st.query_params.clear()
    elif "error" in query_params:
        st.warning("연결이 취소되었습니다.")
        st.query_params.clear()

    connection = _run(auth_svc.get_connection(brand_config.id))

    with st.sidebar:
        st.markdown("---")
        st.markdown("#### 📷 인스타그램 계정")
        if connection and connection.is_active:
            st.success(f"✅ @{connection.instagram_username or '연결됨'}")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🔄 다시 연결", key="ig_re", use_container_width=True):
                    state = str(uuid4())
                    st.session_state["oauth_state"] = state
                    url = auth_svc.generate_oauth_url(state)
                    st.markdown(f'<meta http-equiv="refresh" content="0;url={url}">',
                                unsafe_allow_html=True)
            with c2:
                if st.button("❌ 해제", key="ig_dc", use_container_width=True):
                    _run(auth_svc.revoke_connection(brand_config.id))
                    st.rerun()
        else:
            st.info("📷 계정이 아직 연결되지 않았어요")
            if st.button("🔗 인스타그램 연결하기", key="ig_conn",
                         use_container_width=True):
                state = str(uuid4())
                st.session_state["oauth_state"] = state
                url = auth_svc.generate_oauth_url(state)
                st.markdown(f'<meta http-equiv="refresh" content="0;url={url}">',
                            unsafe_allow_html=True)
    return connection
```
