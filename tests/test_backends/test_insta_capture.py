"""insta_capture 백엔드 테스트.

전체 subprocess 호출은 외부 프로세스라 단위 테스트가 어렵다. 대신 외부에서
분리 가능한 "닫기 버튼 인덱스 파싱" 순수 함수만 단위 테스트한다.
실제 browser-use CLI 호출은 통합 테스트/수동 검증으로 커버.
"""

from backends.insta_capture import parse_close_button_index


class TestParseCloseButtonIndex:
    def test_returns_none_when_no_close_button(self):
        state = """viewport: 1905x1080
page: 1905x1080
scroll: (0, 0)
|scroll element|<div id=scrollview />
        로그인
        가입하기
"""
        assert parse_close_button_index(state) is None

    def test_finds_index_of_role_button_containing_close_svg(self):
        """실제 browser-use state 출력 포맷 기준 ― 닫기 svg 가 속한 role=button 의 인덱스를 반환."""
        state = """[910]<div />
    [22]<div />
        [912]<div />
            [131]<div role=button />
                [914]<svg aria-label=닫기 role=img /> <!-- SVG content collapsed -->
        [132]<span role=link />
        gen_insta_dev님의 사진, 동영상 등 다양한 콘텐츠를 확인해보세요
"""
        assert parse_close_button_index(state) == 131

    def test_finds_index_when_close_has_different_nesting(self):
        """닫기 버튼 인덱스가 세션마다 달라져도 동적으로 찾아야 한다."""
        state = """[80]<div />
    [82]<div role=button />
        [914]<svg aria-label=닫기 role=img />
"""
        assert parse_close_button_index(state) == 82

    def test_ignores_other_aria_labels(self):
        """닫기 외의 다른 aria-label 은 무시한다."""
        state = """[50]<div role=button />
    [51]<svg aria-label=옵션 role=img />
[131]<div role=button />
    [132]<svg aria-label=닫기 role=img />
"""
        assert parse_close_button_index(state) == 131
