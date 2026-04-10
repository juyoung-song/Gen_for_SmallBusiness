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

    def test_real_instagram_state_with_multiple_close_buttons(self):
        """Regression: parnell.official 프로필 실제 state 출력.

        인스타 프로필 페이지는 "관련 계정" 카드들에 각자 '닫기' 버튼을 가지고 있고,
        로그인 모달도 맨 아래에 overlay 로 닫기 버튼을 가진다. 총 닫기 버튼이
        10개 이상 되는데, 우리가 원하는 건 맨 아래 '로그인 모달의' svg 닫기.

        이전 버그: 첫 '닫기' 를 만나 위로 올라가 '관련 계정' 카드의 role=button
        인덱스를 반환 → 엉뚱한 버튼 클릭 → 로그인 모달 그대로 남음.

        올바른 동작: svg role=img + aria-label=닫기 조합만 후보로 삼고,
        마지막 매칭의 위쪽 role=button 인덱스를 반환.
        """
        state = """viewport: 1905x1080
page: 1905x1080
|scroll element|<div id=scrollview />
	[109]<div />
		로그인
		가입하기
		parnell.official
		브랜드
		관련 계정
		[134]<a role=link />
			모두 보기
		|scroll element|<div role=presentation />
			[969]<li />
				[136]<div role=button />
					[137]<button alt=닫기 aria-label=닫기 />
					[138]<a role=link />
			[985]<li />
				[142]<div role=button />
					[143]<button alt=닫기 aria-label=닫기 />
					[144]<a role=link />
			[1001]<li />
				[147]<div role=button />
					[148]<button alt=닫기 aria-label=닫기 />
					[149]<a role=link />
[2075]<div />
	[84]<div />
		[2079]<div />
			[393]<div role=button />
				[2081]<svg aria-label=닫기 role=img /> <!-- SVG content collapsed -->
"""
        # 관련 계정 카드들의 [136], [142], [147] 이 아니라
        # 맨 아래 로그인 모달 overlay 의 [393] 을 반환해야 한다.
        assert parse_close_button_index(state) == 393
