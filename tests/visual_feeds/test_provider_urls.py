import unittest
from unittest.mock import AsyncMock, patch
from sindhu.config.provider_urls import validate_allowed_api_base_url
from sindhu.schemas.system_settings import UpdateSystemSetting
from sindhu.api.routers.v1.system_settings import update


class ProviderUrlsTests(unittest.TestCase):
    def test_validate_allowed_api_base_url_default(self):
        # Valid public host
        self.assertEqual(
            validate_allowed_api_base_url("https://hatyaicityclimate.org"),
            "https://hatyaicityclimate.org",
        )
        # Invalid scheme for public host
        with self.assertRaisesRegex(ValueError, "Public API base URLs must use https"):
            validate_allowed_api_base_url("http://hatyaicityclimate.org")
        # Valid local host
        self.assertEqual(
            validate_allowed_api_base_url("http://localhost"), "http://localhost"
        )
        # Invalid scheme for local host
        with self.assertRaisesRegex(ValueError, "Local API base URLs must use http"):
            validate_allowed_api_base_url("https://localhost")
        # Disallowed host
        with self.assertRaisesRegex(ValueError, "API base URL host is not allowed"):
            validate_allowed_api_base_url("https://evil.com")
        # Disallowed IP
        with self.assertRaisesRegex(ValueError, "API base URL host is not allowed"):
            validate_allowed_api_base_url("http://192.168.1.100")

    def test_validate_allowed_api_base_url_custom_hosts(self):
        # Allow custom proxy
        self.assertEqual(
            validate_allowed_api_base_url(
                "https://my-proxy.com/api", allow_custom_hosts=True
            ),
            "https://my-proxy.com/api",
        )
        # Allow custom IP
        self.assertEqual(
            validate_allowed_api_base_url(
                "http://192.168.1.100", allow_custom_hosts=True
            ),
            "http://192.168.1.100",
        )
        # Still disallows credentials
        with self.assertRaisesRegex(
            ValueError,
            r"API base URL must be an absolute http\(s\) URL without credentials, query, or fragment",
        ):
            validate_allowed_api_base_url(
                "https://user:pass@my-proxy.com/api", allow_custom_hosts=True
            )
        # Disallow link-local (SSRF protection)
        with self.assertRaisesRegex(ValueError, "API base URL host is not allowed"):
            validate_allowed_api_base_url(
                "http://169.254.169.254/latest/meta-data", allow_custom_hosts=True
            )

    def test_validate_allowed_api_base_url_invalid_formats(self):
        with self.assertRaisesRegex(
            ValueError,
            r"API base URL must be an absolute http\(s\) URL without credentials, query, or fragment",
        ):
            validate_allowed_api_base_url("https://hatyaicityclimate.org?test=1")


class SystemSettingsUpdateRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_update_preserves_cctv_overrides_when_omitted(self):
        mock_db_setting = AsyncMock()
        mock_db_setting.hatyai_cctv_api_base_url = "https://hatyaicityclimate.org"
        mock_db_setting.dwr_cctv_api_base_url = "https://telemetry.dwr.go.th/api"
        mock_db_setting.rid_cctv_api_base_url = "http://119.110.213.190"

        with patch(
            "sindhu.api.routers.v1.system_settings.deps.get_system_setting",
            return_value=mock_db_setting,
        ):
            # Payload from old form without CCTV fields
            payload = UpdateSystemSetting.model_validate({"zoom": 12})
            await update(payload, current_user=None)

            mock_db_setting.update.assert_called_once()
            set_query = mock_db_setting.update.call_args[0][0].expression
            self.assertIn("zoom", set_query)
            self.assertEqual(set_query["zoom"], 12)
            self.assertNotIn("hatyai_cctv_api_base_url", set_query)
            self.assertNotIn("dwr_cctv_api_base_url", set_query)
            self.assertNotIn("rid_cctv_api_base_url", set_query)

    async def test_update_clears_cctv_overrides_when_explicitly_null(self):
        mock_db_setting = AsyncMock()
        mock_db_setting.hatyai_cctv_api_base_url = "https://hatyaicityclimate.org"

        with patch(
            "sindhu.api.routers.v1.system_settings.deps.get_system_setting",
            return_value=mock_db_setting,
        ):
            # Payload explicitly passing null to clear the override
            payload = UpdateSystemSetting.model_validate(
                {"zoom": 12, "hatyai_cctv_api_base_url": None}
            )
            await update(payload, current_user=None)

            mock_db_setting.update.assert_called_once()
            set_query = mock_db_setting.update.call_args[0][0].expression
            self.assertIn("zoom", set_query)
            self.assertIn("hatyai_cctv_api_base_url", set_query)
            self.assertIsNone(set_query["hatyai_cctv_api_base_url"])
