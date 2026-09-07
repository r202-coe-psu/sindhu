import unittest
from pydantic import ValidationError
from sindhu.schemas.visual_feeds import PublicVisualFeed
from tests.visual_feeds.test_service import record


class PublicContractTests(unittest.TestCase):
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
