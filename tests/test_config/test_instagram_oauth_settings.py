"""Instagram OAuth surface-specific settings tests."""

from __future__ import annotations

from config.settings import Settings


class TestInstagramOAuthSettings:
    def test_prefers_surface_specific_redirect_uris(self):
        settings = Settings(
            _env_file=None,
            META_REDIRECT_URI="https://legacy.example/callback",
            META_REDIRECT_URI_STREAMLIT="https://streamlit.example/callback",
            META_REDIRECT_URI_MOBILE="https://mobile.example/callback",
        )  # type: ignore[call-arg]

        assert (
            settings.get_meta_redirect_uri("streamlit")
            == "https://streamlit.example/callback"
        )
        assert (
            settings.get_meta_redirect_uri("mobile")
            == "https://mobile.example/callback"
        )

    def test_falls_back_to_legacy_redirect_uri(self):
        settings = Settings(
            _env_file=None,
            META_REDIRECT_URI="https://legacy.example/callback",
            META_REDIRECT_URI_STREAMLIT="",
            META_REDIRECT_URI_MOBILE="",
        )  # type: ignore[call-arg]

        assert (
            settings.get_meta_redirect_uri("streamlit")
            == "https://legacy.example/callback"
        )
        assert (
            settings.get_meta_redirect_uri("mobile")
            == "https://legacy.example/callback"
        )

    def test_checks_oauth_configuration_per_surface(self):
        settings = Settings(
            _env_file=None,
            META_APP_ID="app-id",
            META_APP_SECRET="app-secret",
            TOKEN_ENCRYPTION_KEY="token-key",
            META_REDIRECT_URI_STREAMLIT="https://streamlit.example/callback",
            META_REDIRECT_URI_MOBILE="",
            META_REDIRECT_URI="",
        )  # type: ignore[call-arg]

        assert settings.is_instagram_oauth_configured_for("streamlit") is True
        assert settings.is_instagram_oauth_configured_for("mobile") is False
        assert settings.is_instagram_oauth_configured is True
