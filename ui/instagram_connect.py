"""사이드바 인스타그램 계정 연결 UI 컴포넌트.

기존 app.py의 UI 흐름을 건드리지 않고,
사이드바에 독립적으로 렌더링되는 '플러그인' 형태입니다.
"""

import logging
from uuid import uuid4

import streamlit as st

from utils.async_runner import run_async

logger = logging.getLogger(__name__)


def render_instagram_connection(settings, brand):
    """사이드바에 인스타그램 연결 상태를 표시하고 연결/해제 기능을 제공.

    Args:
        settings: 앱 전역 설정 객체
        brand: 온보딩된 브랜드 설정 (None이면 렌더링 안 함)

    Returns:
        InstagramConnection 인스턴스 또는 None
    """
    if not brand:
        return None

    # OAuth 앱 설정이 안 되어 있으면 UI를 표시하지 않음
    if not settings.META_APP_ID or not settings.META_APP_SECRET:
        return None

    from services.instagram_auth_service import InstagramAuthService

    auth_svc = InstagramAuthService(settings)

    # ── OAuth 콜백 처리 (Meta에서 돌아왔을 때) ──
    query_params = st.query_params

    if "code" in query_params:
        if st.session_state.get("ig_connecting"):
            return None

        received_state = query_params.get("state", "")
        expected_state = st.session_state.get("oauth_state", "")

        if not expected_state or received_state == expected_state:
            try:
                st.session_state.ig_connecting = True
                with st.spinner("🔗 계정 정보를 확인하고 있습니다..."):
                    code = query_params["code"]

                    # code → short token
                    short_token = run_async(auth_svc.exchange_code_for_token(code))
                    # short → long-lived token (60일)
                    long_token, expires_in = run_async(auth_svc.exchange_for_long_lived_token(short_token))
                    
                    try:
                        # 1) IG 비즈니스 계정 정보 자동 조회 시도
                        ig_info = run_async(auth_svc.fetch_instagram_account(long_token))
                        # 2) DB에 암호화 저장
                        run_async(auth_svc.save_connection(brand.id, long_token, expires_in, ig_info))
                        
                        st.success(f"✅ @{ig_info['instagram_username']} 계정이 연결되었습니다!")
                        st.query_params.clear()
                        st.session_state.ig_connecting = False
                        st.rerun()
                    except ValueError as ve:
                        # 자동 조회 실패 시 수동 입력 모드 준비
                        st.warning(f"⚠️ 자동 찾기 실패: {str(ve)}")
                        st.session_state.pending_ig_token = (long_token, expires_in)
                        st.session_state.ig_connecting = False
                        st.query_params.clear()

            except Exception as e:
                logger.error("OAuth 연결 실패: %s", e, exc_info=True)
                st.error(f"❌ 연결 중 오류가 발생했습니다: {e}")
                st.session_state.ig_connecting = False
                st.query_params.clear()
        else:
            st.warning("⚠️ 보안 검증에 실패했습니다. 다시 시도해주세요.")
            st.query_params.clear()

    elif "error" in query_params:
        st.warning("연결이 취소되었습니다.")
        st.query_params.clear()

    # ── 현재 연결 상태 조회 ──
    connection = run_async(auth_svc.get_connection(brand.id))

    # ── 사이드바 UI 렌더링 ──
    with st.sidebar:
        st.markdown("---")
        st.markdown("#### 📷 인스타그램 계정")

        if connection and connection.is_active:
            # 연결된 상태 — username 은 Brand 에 저장됨
            username = brand.instagram_username or "연결됨"
            st.success(f"✅ @{username} 연결됨")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 재연결", key="ig_reconnect", use_container_width=True):
                    state = str(uuid4())
                    st.session_state["oauth_state"] = state
                    oauth_url = auth_svc.generate_oauth_url(state)
                    st.markdown(f'<meta http-equiv="refresh" content="0;url={oauth_url}">', unsafe_allow_html=True)
            with col2:
                if st.button("❌ 해제", key="ig_disconnect", use_container_width=True):
                    run_async(auth_svc.revoke_connection(brand.id))
                    st.rerun()
        else:
            # 미연결 상태
            st.info("📷 인스타그램 계정이 아직 연결되지 않았어요")
            
            if st.button("🔗 자동 연결하기", key="ig_connect", use_container_width=True):
                state = str(uuid4())
                st.session_state["oauth_state"] = state
                oauth_url = auth_svc.generate_oauth_url(state)
                st.markdown(f'<meta http-equiv="refresh" content="0;url={oauth_url}">', unsafe_allow_html=True)

            # ── 수동 입력 섹션 (자동 찾기 실패했을 때만 나타남) ──
            if "pending_ig_token" in st.session_state:
                with st.expander("🛠️ 수동으로 ID 입력하여 연결", expanded=True):
                    st.caption("Meta 보안 설정상 목록 자동 조회가 되지 않습니다.")
                    
                    # 기존 .env ID가 있으면 가이드로 표시
                    old_id = getattr(settings, "INSTAGRAM_ACCOUNT_ID", "")
                    manual_id = st.text_input("Instagram ID 입력", value=old_id, placeholder="1784... 로 시작하는 ID")
                    
                    if st.button("지금 수동 연결 완료", use_container_width=True, type="primary"):
                        try:
                            token, exp = st.session_state.pending_ig_token
                            with st.spinner("정보 확인 중..."):
                                ig_info = run_async(auth_svc.fetch_instagram_account_manually(token, manual_id))
                                run_async(auth_svc.save_connection(brand.id, token, exp, ig_info))
                            
                            del st.session_state.pending_ig_token
                            st.success(f"✅ @{ig_info['instagram_username']} 연결 완료!")
                            st.rerun()
                        except Exception as ex:
                            st.error(f"연결 실패: {ex}")

    return connection
