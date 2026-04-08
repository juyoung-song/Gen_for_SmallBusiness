"""인스타그램 프로필 헤드리스 캡처 백엔드.

Step 2.1 온보딩 파이프라인의 첫 단계로, 사용자가 제공한 인스타 프로필 URL 을
browser-use CLI 로 캡처해 로컬 이미지 파일로 저장한다. 저장된 캡처는 이후
GPT Vision 분석 단계의 입력으로 쓰인다.

설계:
- `parse_close_button_index(state_output)` — browser-use state 출력에서
  로그인 모달 "닫기" 버튼의 인덱스를 찾는 순수 함수 (단위 테스트 대상)
- `InstaCaptureBackend` — subprocess 로 browser-use CLI 를 호출하는 래퍼
  (통합 영역, 실 실행으로만 검증)

browser-use CLI 호출 시퀀스:
  1. browser-use open <url>
  2. browser-use state                         ← 닫기 버튼 인덱스 탐색
  3. browser-use click <idx>                   ← 로그인 모달 닫기
  4. browser-use screenshot <path> --full      ← N번 반복 (count)
  5. browser-use scroll down                   ← 다음 캡처를 위해 스크롤
  6. browser-use close
"""

import logging
import re
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_CLI_COMMAND: tuple[str, ...] = ("uv", "run", "browser-use")


def parse_close_button_index(state_output: str) -> int | None:
    """browser-use `state` 출력에서 "닫기" 버튼의 인덱스를 찾는다.

    browser-use state 출력은 다음과 같은 형태:

        [131]<div role=button />
            [914]<svg aria-label=닫기 role=img />

    위 경우 131 을 반환한다. 없으면 None.

    구현:
    - 'aria-label=닫기' 라인을 찾고, 해당 줄부터 역방향으로 올라가며
      가장 가까운 `[숫자]<... role=button` 라인의 인덱스를 반환한다.
    """
    lines = state_output.splitlines()
    for i, line in enumerate(lines):
        if "aria-label=닫기" not in line:
            continue
        for j in range(i, -1, -1):
            match = re.search(r"\[(\d+)\]<[^>]*role=button", lines[j])
            if match:
                return int(match.group(1))
    return None


class InstaCaptureBackend:
    """browser-use CLI 기반 인스타 프로필 캡처 백엔드.

    name 속성은 ImageBackend/TextBackend 프로토콜의 관례를 따르지만 본 백엔드는
    이미지 생성 백엔드가 아니므로 Protocol 을 구현하지는 않는다.
    """

    name = "insta_capture"

    def __init__(
        self,
        cli_command: tuple[str, ...] = _DEFAULT_CLI_COMMAND,
    ) -> None:
        self.cli_command = cli_command

    def capture_profile(
        self,
        url: str,
        out_dir: Path,
        count: int = 2,
    ) -> list[Path]:
        """인스타 프로필 URL 을 헤드리스로 캡처해 PNG 파일로 저장한다.

        Args:
            url: 인스타 프로필 URL (e.g. https://www.instagram.com/gen_insta_dev/)
            out_dir: 저장 디렉토리. 미존재 시 생성.
            count: 캡처 장수. 기본 2장 (한 화면에 게시물 다수 노출).

        Returns:
            저장된 파일 경로 리스트 (순서 보장).

        Raises:
            RuntimeError: browser-use CLI 호출 실패 시 사용자 친화적 메시지.
        """
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        try:
            self._run(["open", url])
            time.sleep(2)
            self._dismiss_login_modal()

            saved: list[Path] = []
            for i in range(1, count + 1):
                path = out_dir / f"ref_{i}.png"
                logger.info("인스타 캡처 %d/%d → %s", i, count, path)
                self._run(["screenshot", str(path), "--full"])
                saved.append(path)
                if i < count:
                    self._run(["scroll", "down"])
                    time.sleep(2)
            return saved
        except subprocess.CalledProcessError as e:
            logger.error("browser-use CLI 실패 (exit=%s)", e.returncode)
            raise RuntimeError(
                f"인스타 캡처 중 오류가 발생했습니다. "
                f"browser-use 설치 상태를 확인해주세요. (exit={e.returncode})"
            ) from e
        finally:
            # 세션이 남아 있을 수 있으니 정리 시도 (실패해도 무시)
            try:
                self._run(["close"])
            except Exception:
                pass

    # ──────────────────────────────────────────
    # internal helpers
    # ──────────────────────────────────────────
    def _run(self, args: list[str], *, capture: bool = False) -> str:
        """browser-use CLI 호출. capture=True 면 stdout 반환."""
        cmd = list(self.cli_command) + args
        logger.debug("$ %s", " ".join(cmd))
        result = subprocess.run(
            cmd,
            check=True,
            text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.STDOUT if capture else None,
        )
        return result.stdout or ""

    def _dismiss_login_modal(self) -> None:
        """로그인 모달이 떠 있으면 닫기 버튼을 클릭해 제거한다."""
        state = self._run(["state"], capture=True)
        idx = parse_close_button_index(state)
        if idx is None:
            logger.info("로그인 모달 없음 — 그대로 진행")
            return
        logger.info("로그인 모달 닫기 (index=%d)", idx)
        self._run(["click", str(idx)])
        time.sleep(2)
