"""run_async 유틸 테스트 (C-2 버그 수정).

Streamlit 은 매 인터랙션마다 스크립트 전체를 재실행하고 이벤트 루프는 보통
존재하지 않는다. 하지만 코드가 다른 경로에서 불려올 때 (e.g. 테스트 내부
async fixture) 실행 중인 루프가 있을 수 있다. run_async 는 두 상황 모두에서
안전하게 동작해야 한다.

C-2 버그: 기존 구현은 try/except 양쪽 분기 모두 asyncio.run() 호출 →
실행 중인 루프 상황에서 RuntimeError.
"""

import asyncio

import pytest

from utils.async_runner import run_async


async def _sample_coro() -> str:
    await asyncio.sleep(0)
    return "ok"


class TestRunAsync:
    def test_works_when_no_running_loop(self):
        """루프 없을 때 (일반 Streamlit 진입 경로) 정상 동작."""
        result = run_async(_sample_coro())
        assert result == "ok"

    def test_works_when_running_loop_exists(self):
        """실행 중인 루프가 있을 때도 RuntimeError 없이 결과를 반환해야 함."""

        async def _outer():
            # 이 안에서는 루프가 실행 중
            return run_async(_sample_coro())

        result = asyncio.run(_outer())
        assert result == "ok"
