# 🎨 소상공인을 위한 AI 광고 콘텐츠 제작 서비스

## 변경 이력

### [feature/won/img-reference] 로컬 참조 이미지 기반 이미지 생성 (IP-Adapter + SD 1.5)
- 사용자 업로드 사진을 실제 이미지 생성에 반영하는 로컬 추론 파이프라인 구현
- `models/local_backend.py`: `LocalImageBackend` 프로토콜 정의
- `models/sd15.py`: SD 1.5 txt2img 백엔드 (참조 이미지 없을 때 fallback)
- `models/ip_adapter.py`: IP-Adapter + SD 1.5 백엔드 (CLIP cross-attention으로 스타일 반영)
- `models/img2img.py`: SD 1.5 img2img 백엔드 (구도·색감 직접 보존)
- `models/hybrid.py`: IP-Adapter + img2img 하이브리드 백엔드
- `ui/sidebar.py`: 사이드바에서 백엔드/파라미터 실시간 조정 UI (백엔드별 추천값 포함)
- `config/settings.py`: `USE_LOCAL_MODEL`, `LOCAL_BACKEND`, `LOCAL_IMG2IMG_STRENGTH` 등 설정 추가
- `services/image_service.py`: `LOCAL_BACKEND` 값에 따라 백엔드 동적 선택
- Apple Silicon MPS 백엔드 지원, diffusers==0.31.0 + transformers<5.0.0 버전 고정
- **실행 요건**: `USE_LOCAL_MODEL=true` 시 `torch`, `diffusers`, `transformers`, `accelerate`, `torchvision` 필요 (requirements.txt 참조)


### [feature/won/img-analysis] 브랜드 이미지 분석 파이프라인 (실험적)
- `crawl_and_analyze/` 디렉토리 신설 — 크롤링·분석 독립 실행 스크립트 모음
- `crawl_and_analyze/image_crawler.py`: Instaloader 기반 공개 인스타그램 계정 이미지 수집기
  - 현재 인스타그램 403 차단으로 로그인 없이는 미동작 (로그인 연동 예정)
  - 수동으로 이미지를 `image_crawled/{계정명}/` 폴더에 넣어 분석기와 연동 가능
- `crawl_and_analyze/image_analyzer.py`: GPT-5-mini Vision 기반 브랜드 이미지 분석기
  - 로컬 이미지 폴더를 입력으로 받아 개별 이미지 분석 (색감·구도·분위기) 수행
  - 분석 결과를 종합하여 브랜드 톤앤매너 가이드라인 도출
  - 결과를 `image_crawled/{계정명}/brand_analysis.json` 에 저장
  - RGBA PNG → RGB JPEG 자동 변환 처리
  - `responses` API 사용 (gpt-5-mini는 reasoning 모델로 chat completions 미지원)
- **목적**: 신제품 출시 광고 제작 시 기존 브랜드 광고 무드·톤을 참고하기 위한 기반 구축

```bash
# 사용법 (image_crawled/{계정명}/ 폴더에 이미지 직접 배치 후 실행)
cd crawl_and_analyze
python image_analyzer.py --dir image_crawled/torriden_official --limit 9
```

## 1. 프로젝트 소개
마케팅 전담 인력이 부족한 소상공인(1인 사업자, 초기 창업자)을 위해 자체적으로 광고 문구와 이미지를 손쉽게 생성하고, **인스타그램에 바로 자동 업로드까지** 할 수 있는 생성형 AI 서비스입니다. 
빠른 기획 및 MVP 검증을 목적으로 1인 개발 환경에서 구축되었으며, 입력 화면부터 API 연동, 인스타 피드 포스팅까지 단일 페이지에서 원활하게 동작하도록 구성되었습니다.

## 2. 문제 정의
- **시간과 인력 부족**: 소상공인은 제품 개발과 매장 운영만으로도 시간이 빠듯하여 마케팅 콘텐츠 기획에 많은 시간을 투자하기 어렵습니다.
- **디자인 역량 부족**: 상용 툴을 학습하거나 전문 디자이너를 고용하기에는 비용과 러닝커브가 높습니다.
- **비용 문제**: 지속적인 온/오프라인 홍보를 위해 배너, 전단지, SNS 피드 등을 매번 외주 대행사에 맡기면 큰 고정 비용이 발생합니다.

**💡 해결책:** 제품명과 간단한 설명, 그리고 원하는 분위기(스타일)만 고르면 AI가 광고 텍스트와 썸네일을 즉석에서 만들어주는 직관적인 솔루션을 제공합니다.

## 3. 주요 기능

1. **전략적 홍보 문구 생성**: 상품명과 상세 정보는 물론, '신상품 홍보', '할인 행사' 등 **마케팅 목적(Goal)**에 최적화된 카피를 생성합니다.
2. **AI 광고 비주얼 생성**: 선택한 홍보 목적과 스타일에 맞춰 상업용 광고 수준의 이미지를 생성하며, 업로드한 사진의 구도와 색감을 참고합니다.
3. **인스타그램 피드 & 스토리 최적화**: 
    - **피드(1:1)**: 게시물용 캡션과 해시태그를 포함한 업로드 지원.
    - **스토리(9:16)**: 생성된 문구를 이미지 위에 아름답게 합성하여 즉시 업로드 가능한 세로형 콘텐츠 제작.
4. **콘텐츠 히스토리 관리**: 과거에 만들었던 멋진 홍보물들을 언제든 다시 확인하고 다운로드할 수 있습니다.
- **직관적인 콘텐츠 입력**: 상품명(필수), 상품 설명(선택), 5가지 광고 스타일(기본, 감성, 고급, 유머, 심플) 중 선택.
- **광고 문구 자동 생성**: 선택한 톤앤매너에 맞춘 3가지 짧은 광고 카피와 2개의 확장형 홍보 문장 제공.
- **광고 이미지 자동 생성**: 입력된 정보와 스타일을 기반으로 AI가 알맞은 프롬프트를 재구성하여 광고용 1:1 썸네일(1024x1024) 생성.
- **재생성 및 다운로드**: 결과물이 마음에 들지 않을 시 원클릭 `재생성` 기능 및 생성물을 `.txt`, `.png` 파일로 로컬 스토리지에 다운로드 지원.
- **[NEW] 히스토리 아카이브**: 내가 생성했던 모든 광고 문구와 이미지가 SQLite 데이터베이스에 비동기로 자동 저장되며, 언제든지 `히스토리 아카이브` 탭에서 다시 열람하고 다운로드할 수 있습니다.
- **[NEW] 한글 자동 번역 & 다중 벤더 파이프라인**: 오픈소스 이미지 AI의 한글 인식 한계를 극복하기 위해, 사용자가 한글을 입력하면 GPT-5-mini가 고품질의 영어 프롬프트로 실시간 번역하여 Hugging Face(FLUX/SDXL) 모델에 전달합니다. 사장님은 영어 걱정 없이 100% 한국어로만 편리하게 쓸 수 있습니다.
- **안전한 모드 전환**: 무분별한 API 토큰 비용을 방지하기 위해 로컬 테스트 전용 데이터(더미 마크다운, 그라데이션 Pillow 썸네일)를 반환하는 Mock 검증 모드 내장.

## 4. 기술 스택
- **Language**: Python 3.11+
- **Frontend / UI**: Streamlit `1.30+`
- **Backend / Datatype**: Pydantic `2.0+`, Pydantic-Settings `2.0+`
- **Database / ORM**: `SQLAlchemy 2.0+`, `aiosqlite` (SQLite 기반 비동기 처리)
- **AI / External API**: `openai>=1.40`, `httpx`
- **Image Processing**: `Pillow` (JPEG 변환 및 Mock 모드)
- **Instagram 연동**: `requests` (Meta Graph API · FreeImage.host API)

## 5. 디렉토리 구조
```text
.
├── app.py                   # Streamlit 메인 파일 (새로 만들기 / 아카이브 멀티 탭 및 UI 라우팅)
├── config/
│   ├── __init__.py
│   ├── database.py          # SQLAlchemy 비동기 세션 팩토리 및 DB 초기화
│   └── settings.py          # 환경변수(.env) 로드 및 앱 런타임 설정 관리
├── models/
│   ├── __init__.py
│   ├── base.py              # TimestampMixin을 포함한 ORM 베이스
│   └── history.py           # 생성 내역 저장을 위한 History 테이블 모델
├── schemas/
│   ├── __init__.py
│   ├── history_schema.py    # DB 입출력을 위한 히스토리 검증 Pydantic 모델
│   ├── image_schema.py      # 이미지 생성 입출력 페이로드 Pydantic 검증
│   └── text_schema.py       # 문구 생성 입출력 페이로드 Pydantic 검증
├── services/
│   ├── __init__.py
│   ├── instagram_service.py # Meta API 및 FreeImage 연동 업로드 로직
│   ├── history_service.py   # 비동기 DB 삽입 및 전체 과거 내역 조회 로직
│   ├── image_service.py     # 영문 1차 번역 후 외부 이미지 생성(Hugging Face) 및 파일 시스템 저장 병합
│   └── text_service.py      # 텍스트 모델(GPT) 통신 로직
├── utils/
│   ├── __init__.py
│   └── prompt_builder.py    # 사용자의 입력을 AI가 이해하기 쉬운 System/User 프롬프트로 변환
├── docs/                    # PRD, Architecture 등 기획 문서
├── .env                     # [Local] 환경 변수 및 보안 키 (Git 제외 대상)
├── requirements.txt         # 패키지 의존성 명세
└── README.md                # 프로젝트 가이드
```

## 6. 실행 방법
```bash
# 1. 가상환경 생성 및 활성화
python3 -m venv venv
source venv/bin/activate  # Mac/Linux
# venv\Scripts\activate   # Windows

# 2. 패키지 설치
pip install -r requirements.txt

# 3. 환경 변수 설정 (다음 7번 항목 참조)
cp .env.example .env

# 4. 서비스 실행
streamlit run app.py
```

## 7. 환경 변수 설정
`.env` 파일을 앱 최상단 경로에 두고 다음과 같이 구성합니다. (동적 변경 시 `streamlit` 서버를 재시작해야 반영됩니다)

```env
# ── AI API Keys ──
OPENAI_API_KEY=sk-proj-...  # 발급받은 실제 OpenAI API 키 입력
HUGGINGFACE_API_KEY=hf_...  # Hugging Face Access Token 입력

# ── Application ──
APP_ENV=development
LOG_LEVEL=INFO
USE_MOCK=false              # false: 실제 AI 모델 호출 / true: 로컬 가상 코드 반환

# ── Model Settings ──
TEXT_MODEL=gpt-5-mini                         # 사용 텍스트 모델
IMAGE_MODEL=black-forest-labs/FLUX.1-schnell  # 사용 이미지 모델 (Hugging Face)
IMAGE_SIZE=1024x1024
IMAGE_QUALITY=standard

# ── Instagram Upload Settings ──
IMGBB_API_KEY=your-imgbb-key          # (레거시, 사용하지 않음)
META_ACCESS_TOKEN=EAA...              # Facebook System User 영구 토큰
INSTAGRAM_ACCOUNT_ID=178...           # 인스타그램 비즈니스 계정 ID

# ── API Request Settings (안정성) ──
TEXT_TIMEOUT=30.0          
IMAGE_TIMEOUT=60.0         
TEXT_TEMPERATURE=0.8       
TEXT_MAX_TOKENS=1000       
```

## 8. mock / 실제 API 전환 방법
**Mock 모드 (`USE_MOCK=true`)**
- 개발 초기 UI/UX 검증용 테스트 모드입니다.
- `text_service.py`와 `image_service.py` 내부의 하드코딩된 더미 텍스트 묶음과 `Pillow`로 그린 그라데이션 이미지를 즉시 반환합니다.
- OpenAI API 호출 코스트가 전혀 들지 않으며, 인터넷 연결이나 API Key가 없어도 UI 전체 흐름을 테스트할 수 있습니다.

**실제 API 모드 (`USE_MOCK=false`)**
- `OPENAI_API_KEY`가 유효한지 사전에 검증하며, 서비스 레이어에서 OpenAI SDK를 통해 HTTP 요청을 수행합니다.
- 지정된 `TEXT_MODEL`을 통해 창의적인 실제 문장을 생성하고 `IMAGE_MODEL`을 통해 URL에서 렌더링된 썸네일 바이트를 받아옵니다.
- 인스타그램 업로드 버튼 클릭 시, 생성된 이미지를 JPEG 변환 → FreeImage.host 호스팅 → Meta Graph API를 거쳐 실제 인스타그램 피드에 자동 포스팅됩니다.
- Streamlit 하단 푸터에 "모드: API"로 표시되어 현재 과금 요청 모드인지 명확하게 파악할 수 있습니다.

## 9. 예시 화면 흐름
1. **입력 단계**: 사용자가 상품명란에 "수제 마카롱", 상품 설명란에 "프랑스 이즈니 버터와 동물성 생크림을 듬뿍 넣은", 스타일은 "감성"을 선택.
2. **생성 단계**: 생성 버튼 클릭 시, "텍스트 모델을 생성하고 있습니다 (gpt-4o-mini)" 로딩 표출.
3. **결과 출출 단계**: 
   - [💡 광고 문구 3종] "🌸 작은 상자 속 피어나는 버터의 향, 당신의 일상에 건네는 수제 마카롱" 등
   - [📣 홍보 문장 2종] "수제 마카롱이 가장 맛있는 오후 세 시, 따뜻한 커피 한 잔과 곁들여보세요..."
4. **활용 단계**: 결과물이 적합하다면 `📥 문구 다운로드` 버튼으로 .txt 파일 저장. 톤앤매너 변경을 원하면 다시 옵션을 바꾸거나 `🔄 재생성` 버튼 클릭!

## 10. 향후 개선 방향
- **문구+이미지 통합 동시 생성**: 현재는 텍스트와 이미지를 별도 생성하지마만, 사용성을 높이기 위해 텍스트 스토리를 배경으로 한 자동 병렬 호출 태스크 구조(async 파이프라인/Celery) 도입.
- **다국어 글로벌 마케팅 시스템 연동**: 해외 플랫폼(아마존, 엣시, 쇼피) 판매자를 위해, 프롬프트를 영어, 일본어 등으로 파이프라인을 두 번 태워 번역 버전을 제공하는 LLM Chain 업그레이드.
- **예약 업로드**: 날짜와 시간을 지정하여 예약된 시간에 자동으로 인스타그램에 포스팅하는 기능.
- **다중 SNS 연동 확장**: 인스타그램 외에 네이버 블로그, 카카오 채널 등 추가 SNS에도 동시 업로드 가능하도록 플러그인 구조 확장.
- **광고 성과 분석 대시보드**: 업로드한 게시물의 좋아요/댓글 수를 추적하여 어떤 콘텐츠가 효과적인지 분석해주는 기능.
