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
  2. browser-use state                                  ← 닫기 버튼 인덱스 탐색
  3. browser-use click <idx>                            ← 로그인 모달 닫기
  4. browser-use screenshot <path>                      ← viewport 캡처 (1905x1080)
  5. browser-use scroll down --amount <SCROLL_AMOUNT>   ← 다음 캡처를 위해 스크롤
  6. (4-5 반복 count 회)
  7. browser-use close

설계 메모:
- `--full` 플래그를 일부러 쓰지 않는다. --full 은 페이지 전체를 한 번에 찍기
  때문에 "스크롤 후 다른 영역" 캡처가 무의미해진다 (모든 캡처가 같은 풀페이지가 됨).
- 대신 viewport 단위로 찍고 viewport 만큼 스크롤 → 매 캡처가 실제로 다른 영역.
- SCROLL_AMOUNT 는 viewport 높이(1080) 보다 약간 작게 잡아 약간 겹침을 허용
  (그리드 행 경계 잘림 방지).
"""

import logging
import re
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_CLI_COMMAND: tuple[str, ...] = ("browser-use",)

# 캡처 간 스크롤 양 (px). viewport 1080 보다 약간 작게 → 그리드 행 경계 약간 겹침.
_SCROLL_AMOUNT_PX = 900


def detect_unusable_instagram_state(state_output: str) -> str | None:
    """browser-use state 가 분석 가능한 인스타 프로필 화면인지 판별한다."""
    normalized = state_output.lower()
    if "http error 429" in normalized:
        return "Instagram이 VM/브라우저 세션 요청을 HTTP 429로 제한했습니다."
    if "accounts/login" in normalized:
        return "Instagram 로그인 페이지로 이동되어 프로필 화면을 볼 수 없습니다."
    if "this page isn" in normalized and "working" in normalized:
        return "Instagram 오류 페이지가 표시되어 프로필 화면을 볼 수 없습니다."
    return None


def parse_close_button_index(state_output: str) -> int | None:
    """browser-use `state` 출력에서 로그인 모달 "닫기" 버튼의 인덱스를 찾는다.

    인스타 프로필 페이지에는 '닫기' 라벨이 여러 종류 존재:

    1) "관련 계정" 카드의 작은 X 버튼들 (여러 개, `button alt=닫기`)
    2) 로그인 유도 overlay 모달의 진짜 X 버튼 (맨 아래, `svg aria-label=닫기 role=img`)

    우리는 (2) 만 원한다. 전략:
    - `svg ... aria-label=닫기 role=img` 패턴만 후보로 (관련 계정 카드의
      `button alt=닫기` 는 제외)
    - 그 중 **가장 마지막** 매칭의 위쪽 `[숫자]<... role=button` 인덱스 반환
      (overlay 는 DOM 트리 끝에 붙으므로)

    없으면 None.
    """
    lines = state_output.splitlines()

    # 로그인 모달 후보: svg + role=img + aria-label=닫기 가 같은 라인에 있어야 함
    candidate_line_idx: int | None = None
    for i, line in enumerate(lines):
        if "svg" in line and "aria-label=닫기" in line and "role=img" in line:
            candidate_line_idx = i  # 마지막 매칭을 유지

    if candidate_line_idx is None:
        return None

    # 후보 라인에서 위로 올라가 가장 가까운 role=button 인덱스 반환
    for j in range(candidate_line_idx, -1, -1):
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
            self._assert_profile_page_usable()

            saved: list[Path] = []
            for i in range(1, count + 1):
                self._assert_profile_page_usable()
                path = out_dir / f"ref_{i}.png"
                logger.info("인스타 캡처 %d/%d → %s", i, count, path)
                # viewport 캡처 (--full 미사용 — 매 캡처가 다른 영역이 되도록)
                self._run(["screenshot", str(path)])
                saved.append(path)
                if i < count:
                    self._run(
                        ["scroll", "down", "--amount", str(_SCROLL_AMOUNT_PX)]
                    )
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

    def _assert_profile_page_usable(self) -> None:
        """429/login/error 페이지를 GPT Vision 분석 입력으로 넘기지 않도록 차단한다."""
        state = self._run(["state"], capture=True)
        reason = detect_unusable_instagram_state(state)
        if reason is None:
            return
        logger.warning("인스타 캡처 중단: %s", reason)
        raise RuntimeError(f"인스타그램 캡처 화면이 분석 가능한 프로필이 아닙니다. {reason}")
