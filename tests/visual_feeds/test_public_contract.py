import unittest
from pydantic import ValidationError
from sindhu.schemas.visual_feeds import PublicVisualFeed
from tests.visual_feeds.test_service import record


class PublicContractTests(unittest.TestCase):
    def test_provider_base_url_environment_and_database_overrides(self):
        import os
        from unittest.mock import patch

        from sindhu.api.core.settings.app import AppSettings
        from sindhu.config.provider_urls import resolve_provider_base_urls
        from sindhu.schemas.system_settings import SystemSetting

        with patch.dict(
            os.environ,
            {
                "HATYAI_CCTV_API_BASE_URL": "http://localhost:8080/hatyai",
                "DWR_CCTV_API_BASE_URL": "http://127.0.0.1:8081/dwr",
                "RID_CCTV_API_BASE_URL": "http://host.docker.internal:8082/rid",
            },
        ):
            settings = AppSettings()

        self.assertEqual(
            settings.HATYAI_CCTV_API_BASE_URL, "http://localhost:8080/hatyai"
        )
        self.assertEqual(
            settings.DWR_CCTV_API_BASE_URL, "http://127.0.0.1:8081/dwr"
        )
        self.assertEqual(
            settings.RID_CCTV_API_BASE_URL, "http://host.docker.internal:8082/rid"
        )

        database_override = SystemSetting(
            hatyai_cctv_api_base_url="http://localhost:8083/hatyai"
        )
        resolved = resolve_provider_base_urls(database_override, settings)
        self.assertEqual(resolved["hatyai"], "http://localhost:8083/hatyai")
        self.assertEqual(resolved["dwr"], "http://127.0.0.1:8081/dwr")

    def test_provider_base_url_settings_have_public_defaults(self):
        from sindhu.api.core.settings.app import AppSettings

        settings = AppSettings()
        self.assertEqual(
            settings.HATYAI_CCTV_API_BASE_URL, "https://hatyaicityclimate.org"
        )
        self.assertEqual(
            settings.DWR_CCTV_API_BASE_URL, "https://telemetry.dwr.go.th/api"
        )
        self.assertEqual(settings.RID_CCTV_API_BASE_URL, "http://119.110.213.190")

    def test_secrets_are_not_accepted_in_public_dto(self):
        for payload in [
            record(raw_payload={"token": "secret"}),
            record(token="secret"),
            record(
                attribution={
                    "provider": "Hatyai",
                    "source_url": "https://hatyaicityclimate.org",
                    "token": "secret",
                }
            ),
        ]:
            with (
                self.subTest(payload=list(payload)),
                self.assertRaises(ValidationError),
            ):
                PublicVisualFeed.model_validate(payload)

    def test_unsafe_image_urls(self):
        for url in [
            "http://hatyaicityclimate.org/x.jpg",
            "https://user:pass@hatyaicityclimate.org/x.jpg",
            "https://hatyaicityclimate.org/x.jpg?token=secret",
            "https://hatyaicityclimate.org:9000/x.jpg",
            "https://attacker.invalid/x.jpg",
            "//attacker.invalid/x.jpg",
            "https://hatyaicityclimate.org\\@attacker.invalid/x.jpg",
        ]:
            with self.subTest(url=url), self.assertRaises(ValidationError):
                PublicVisualFeed.model_validate(record(image_url=url))

    def test_strict_timestamps_and_mutable_version(self):
        with self.assertRaises(ValidationError):
            PublicVisualFeed.model_validate(record(captured_at="2026-09-03 11:00:00"))
        feed = PublicVisualFeed.model_validate(record())
        self.assertTrue(feed.image_url.endswith("?v=123"))
        self.assertNotIn("raw_payload", feed.model_dump())
