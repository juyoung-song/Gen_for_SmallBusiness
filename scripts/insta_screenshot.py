"""인스타그램 프로필 URL을 입력받아 헤드리스로 스크린샷 3장을 저장한다.

browser-use CLI를 subprocess로 호출하는 래퍼.

사용:
    python scripts/insta_screenshot.py
    python scripts/insta_screenshot.py https://www.instagram.com/gen_insta_dev/
    python scripts/insta_screenshot.py https://www.instagram.com/gen_insta_dev/ --out shots --count 3
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path


BROWSER_USE = ["uv", "run", "browser-use"]


def run(args: list[str], *, capture: bool = False) -> str:
    """browser-use CLI 호출. capture=True면 stdout 반환."""
    cmd = BROWSER_USE + args
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    return result.stdout or ""


def find_close_button_index(state_output: str) -> int | None:
    """state 출력에서 '닫기' aria-label 가진 요소의 인덱스를 찾는다.

    state 출력 예:
        [131]<div role=button />
            [914]<svg aria-label=닫기 role=img />
    → 131 반환 (svg의 부모 div index)
    """
    lines = state_output.splitlines()
    for i, line in enumerate(lines):
        if "aria-label=닫기" in line:
            # 현재 줄 위에서 가장 가까운 [숫자]<...role=button> 찾기
            for j in range(i, -1, -1):
                m = re.search(r"\[(\d+)\]<[^>]*role=button", lines[j])
                if m:
                    return int(m.group(1))
    return None


def dismiss_login_modal() -> None:
    """로그인 모달이 있으면 닫는다."""
    print("[*] 로그인 모달 확인 중...")
    state = run(["state"], capture=True)
    idx = find_close_button_index(state)
    if idx is None:
        print("[*] 모달 없음 — 그대로 진행")
        return
    print(f"[*] 닫기 버튼 인덱스 {idx} → 클릭")
    run(["click", str(idx)])
    time.sleep(2)


def capture(url: str, out_dir: Path, count: int) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []

    print(f"[*] 페이지 열기: {url}")
    run(["open", url])
    time.sleep(2)

    dismiss_login_modal()

    for i in range(1, count + 1):
        path = out_dir / f"shot_{i}.png"
        print(f"[*] 스크린샷 {i}/{count} → {path}")
        run(["screenshot", str(path), "--full"])
        saved.append(path)
        if i < count:
            run(["scroll", "down"])
            time.sleep(2)

    print("[*] 세션 종료")
    run(["close"])
    return saved


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="인스타 프로필 스크린샷 캡처")
    p.add_argument("url", nargs="?", help="인스타 URL (생략 시 입력 프롬프트)")
    p.add_argument("--out", default="shots", help="저장 디렉토리 (기본: shots)")
    p.add_argument("--count", type=int, default=3, help="스크린샷 장수 (기본: 3)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    url = args.url or input("인스타 URL을 입력하세요: ").strip()
    if not url:
        print("URL이 필요합니다.", file=sys.stderr)
        return 1

    try:
        saved = capture(url, Path(args.out), args.count)
    except subprocess.CalledProcessError as e:
        print(f"[!] browser-use CLI 실패 (exit {e.returncode})", file=sys.stderr)
        # 세션이 열려 있을 수 있으니 정리 시도
        subprocess.run(BROWSER_USE + ["close"], check=False)
        return e.returncode

    print(f"\n완료. {len(saved)}장 저장:")
    for p in saved:
        print(f"  - {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
