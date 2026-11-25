import unittest

from sindhu.config.provider_urls import validate_allowed_api_base_url


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
