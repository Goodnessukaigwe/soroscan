from soroscan import settings as app_settings


class TestAllowedOriginsConfiguration:
    def test_single_origin_parsing(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:3000")

        import importlib
        importlib.reload(app_settings)

        assert app_settings.CORS_ALLOWED_ORIGINS == ["http://localhost:3000"]

    def test_multiple_origins_parsing(self, monkeypatch):
        monkeypatch.setenv(
            "ALLOWED_ORIGINS",
            "http://localhost:3000,http://localhost:5173,https://app.example.com",
        )

        import importlib
        importlib.reload(app_settings)

        assert app_settings.CORS_ALLOWED_ORIGINS == [
            "http://localhost:3000",
            "http://localhost:5173",
            "https://app.example.com",
        ]

    def test_empty_origins_returns_empty_list(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_ORIGINS", "")

        import importlib
        importlib.reload(app_settings)

        assert app_settings.CORS_ALLOWED_ORIGINS == []

    def test_production_url_parsing(self, monkeypatch):
        monkeypatch.setenv(
            "ALLOWED_ORIGINS",
            "https://soroscan.example.com,https://www.soroscan.example.com",
        )

        import importlib
        importlib.reload(app_settings)

        assert app_settings.CORS_ALLOWED_ORIGINS == [
            "https://soroscan.example.com",
            "https://www.soroscan.example.com",
        ]

    def test_whitespace_handling(self, monkeypatch):
        monkeypatch.setenv(
            "ALLOWED_ORIGINS",
            "http://localhost:3000 , https://app.example.com , http://localhost:5173",
        )

        import importlib
        importlib.reload(app_settings)

        assert app_settings.CORS_ALLOWED_ORIGINS == [
            "http://localhost:3000",
            "https://app.example.com",
            "http://localhost:5173",
        ]