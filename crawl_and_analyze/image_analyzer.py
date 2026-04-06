"""GPT Vision 이미지 분석.

로컬 이미지 폴더를 읽어 GPT-5-mini Vision으로 각 이미지를 분석하고
브랜드 톤앤매너를 종합합니다. 결과는 해당 브랜드 폴더에 brand_analysis.json으로 저장됩니다.

사용:
    python image_analyzer.py --dir image_crawled/torriden_official
    python image_analyzer.py --dir image_crawled/torriden_official --limit 9 --model gpt-5-mini
"""

import argparse
import base64
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# 프로젝트 루트의 .env 로드 (crawl_and_analyze/ 안에서 실행해도 찾을 수 있도록)
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def load_image_as_base64(path: Path) -> str:
    """로컬 이미지 파일을 base64 data URL로 변환합니다.

    RGBA 이미지는 흰 배경에 합성하여 RGB JPEG로 변환합니다.
    OpenAI vision API는 투명 채널(알파)을 안정적으로 처리하지 못합니다.
    """
    from PIL import Image
    import io

    img = Image.open(path)
    if img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    data = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{data}"


# ── 분석 프롬프트 ─────────────────────────────────
_SINGLE_IMAGE_SYSTEM = """당신은 브랜드 비주얼 전략 전문가입니다.
광고 이미지를 분석하여 아래 항목을 한국어로 출력하세요.

[색감]
- 주조색, 보조색, 전체적인 색온도 (따뜻함/차가움/중립)
- 채도·명도 특징

[구도]
- 피사체 배치 (중앙/여백 중심/비대칭 등)
- 시선 흐름, 여백 활용

[분위기 & 소품]
- 전체적인 감성 키워드 (예: 미니멀, 청량, 고급, 자연친화)
- 등장하는 소품, 배경 요소

출력 형식: 위 항목 그대로, 간결하게."""

_BRAND_SYNTHESIS_SYSTEM = """당신은 브랜드 전략 컨설턴트입니다.
여러 광고 이미지 분석 결과를 종합하여 브랜드의 일관된 톤앤매너를 도출하세요.

[브랜드 톤앤매너 종합]
1. 시그니처 색감 팔레트
2. 구도·레이아웃 패턴
3. 감성 키워드 (3~5개)
4. 반복 등장하는 소품·배경 요소
5. 신제품 광고 제작 시 반드시 지킬 비주얼 가이드라인 (3가지)

이 브랜드의 새 광고를 만들 때 참고할 수 있도록 실용적으로 작성하세요."""


def analyze_single_image(client: OpenAI, model: str, image_src: str, label: str, index: int) -> str:
    """단일 이미지(base64 data URL 또는 https URL)를 GPT Vision으로 분석합니다.

    gpt-5-mini는 reasoning 모델이므로 responses API + input_image 타입을 사용합니다.
    """
    print(f"  [{index}] 분석 중: {label}")
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": _SINGLE_IMAGE_SYSTEM + "\n\n위 이미지를 분석해주세요."},
                    {"type": "input_image", "image_url": image_src},
                ],
            }
        ],
        max_output_tokens=1000,
    )
    content = (response.output_text or "").strip()

    if not content:
        print(f"  ⚠️  응답 비어있음")
    else:
        print(f"  ✓ 완료")

    return content


def synthesize_brand_tone(client: OpenAI, model: str, analyses: list[str]) -> str:
    """개별 분석 결과들을 종합하여 브랜드 톤앤매너를 도출합니다."""
    combined = "\n\n---\n\n".join(
        f"[이미지 {i+1} 분석]\n{a}" for i, a in enumerate(analyses)
    )
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": _BRAND_SYNTHESIS_SYSTEM + f"\n\n다음은 {len(analyses)}개 광고 이미지 분석 결과입니다:\n\n{combined}",
            }
        ],
        max_output_tokens=1200,
    )
    return (response.output_text or "").strip()


def main():
    parser = argparse.ArgumentParser(description="GPT Vision 브랜드 이미지 분석기")
    parser.add_argument("--dir", required=True, help="로컬 이미지 폴더 (예: image_crawled/torriden_official)")
    parser.add_argument("--limit", type=int, default=9, help="분석할 이미지 수")
    parser.add_argument("--model", default="gpt-5-mini", help="사용할 GPT 모델")
    args = parser.parse_args()

    # OpenAI 클라이언트
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        print("[오류] OPENAI_API_KEY가 없습니다. 프로젝트 루트의 .env를 확인하세요.")
        return
    client = OpenAI(api_key=api_key)

    # 이미지 파일 목록
    img_dir = Path(args.dir)
    if not img_dir.exists():
        print(f"[오류] 폴더 없음: {img_dir}")
        return

    files = sorted(f for f in img_dir.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS)
    files = files[: args.limit]
    if not files:
        print(f"[오류] {img_dir} 에 이미지 파일이 없습니다.")
        return

    brand_name = img_dir.name
    print(f"[분석기] '{brand_name}' — {len(files)}개 이미지 분석 시작 (model={args.model})")

    # 개별 이미지 분석
    analyses = []
    for i, f in enumerate(files, 1):
        try:
            image_src = load_image_as_base64(f)
            result = analyze_single_image(client, args.model, image_src, f.name, i)
            analyses.append({"filename": f.name, "analysis": result})
            if result:
                print(f"{result}\n{'─'*50}")
        except Exception as e:
            print(f"  → [오류] {e}")
            analyses.append({"filename": f.name, "analysis": f"오류: {e}"})

    # 브랜드 톤앤매너 종합
    valid = [a["analysis"] for a in analyses if a["analysis"] and not a["analysis"].startswith("오류")]
    brand_tone = ""
    if valid:
        print(f"\n[분석기] 브랜드 톤앤매너 종합 중 ({len(valid)}개 분석 결과 기반)...")
        try:
            brand_tone = synthesize_brand_tone(client, args.model, valid)
            print(f"\n{'━'*60}")
            print("【 브랜드 톤앤매너 종합 】")
            print(f"{'━'*60}")
            print(brand_tone)
        except Exception as e:
            print(f"[오류] 종합 분석 실패: {e}")
            brand_tone = f"오류: {e}"
    else:
        print("[경고] 유효한 분석 결과가 없어 종합을 건너뜁니다.")

    # 결과를 브랜드 폴더 안에 저장
    output_path = img_dir / "brand_analysis.json"
    output = {
        "brand": brand_name,
        "model": args.model,
        "image_count": len(analyses),
        "individual_analyses": analyses,
        "brand_tone_summary": brand_tone,
    }
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"\n[분석기] 결과 저장: {output_path}")


if __name__ == "__main__":
    main()
