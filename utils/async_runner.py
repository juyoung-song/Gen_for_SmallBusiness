"""Streamlit 환경에서 async 코루틴 실행 유틸.

Streamlit 은 매 인터랙션마다 스크립트를 재실행하므로 이벤트 루프가 존재하지
않는 것이 일반적이다. 하지만 코드가 테스트나 다른 async 컨텍스트에서 호출되면
실행 중인 루프가 있을 수 있다. 두 상황 모두에서 안전해야 한다.

C-2 버그: 기존 app.py 의 run_async 는 try/except 양쪽 분기 모두
asyncio.run() 을 호출해서 실행 중인 루프 상황에서 RuntimeError 가 났다.
본 모듈은 실행 중 루프가 감지되면 별도 스레드의 루프로 안전하게 실행한다.
"""

import asyncio
import concurrent.futures
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """async 코루틴을 동기 컨텍스트에서 안전하게 실행한다.

    - 실행 중인 이벤트 루프가 없으면 asyncio.run() 으로 실행 (일반 경로)
    - 실행 중인 루프가 있으면 별도 스레드의 임시 루프에서 실행
      (asyncio.run() 은 nested loop 를 지원하지 않음)
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # 실행 중 루프 없음 → 가장 흔한 경로
        return asyncio.run(coro)

    # 실행 중 루프 있음 → 별도 스레드에서 새 루프로 실행
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()
