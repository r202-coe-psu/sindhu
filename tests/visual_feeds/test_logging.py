import asyncio
import unittest
from unittest.mock import patch

import httpx

from sindhu.services import cctv_logging
from sindhu.services.cctv_errors import SourceError

SECRET_URL = "https://user:secret@provider.example.test/cams?token=abc"


def _wrapped(cause: BaseException, code: str = "source_error") -> SourceError:
    """Raise ``cause`` and convert it the way providers do (``from None``)."""
    try:
        try:
            raise cause
        except BaseException:
            raise SourceError(code) from None
    except SourceError as error:
        return error


class CctvLoggingTests(unittest.TestCase):
    def setUp(self):
        cctv_logging.reset_repeat_limit()

    def _log(self, error: BaseException) -> list[str]:
        with self.assertLogs(cctv_logging.logger, level="WARNING") as captured:
            cctv_logging.log_failure("hatyai_city_climate history", "public", error)
        return captured.output

    def test_upstream_failure_is_a_warning_with_the_original_type(self):
        error = _wrapped(httpx.ConnectError(SECRET_URL), code="transport_error")

        (line,) = self._log(error)

        self.assertTrue(line.startswith("WARNING:"))
        self.assertIn("code=transport_error", line)
        self.assertIn("cause=ConnectError", line)

    def test_bug_hidden_behind_source_error_is_an_error_with_location(self):
        error = _wrapped(KeyError("photos"))

        (line,) = self._log(error)

        self.assertTrue(line.startswith("ERROR:"))
        self.assertIn("cause=KeyError", line)
        self.assertIn("raised_at=test_logging.py:", line)

    def test_exception_messages_never_reach_the_log(self):
        for cause in (httpx.ConnectError(SECRET_URL), ValueError(SECRET_URL)):
            with self.subTest(cause=type(cause).__name__):
                (line,) = self._log(_wrapped(cause))
                self.assertNotIn("secret", line)
                self.assertNotIn("provider.example.test", line)

    def test_repeats_of_one_failure_are_held_back_and_counted(self):
        error = _wrapped(httpx.ConnectError(SECRET_URL), code="transport_error")
        with self.assertLogs(cctv_logging.logger, level="WARNING") as captured:
            for _ in range(3):
                cctv_logging.log_failure("rid catalog", "public", error)
            cctv_logging.log_failure("rid catalog", "public", _wrapped(KeyError("x")))

        self.assertEqual(len(captured.output), 2)
        self.assertIn("repeats=0", captured.output[0])

        with patch.object(cctv_logging.time, "monotonic", return_value=1e12):
            (line,) = self._log(error)
        self.assertIn("repeats=2", line)

    def test_cancellation_is_not_reported_as_the_cause_of_a_timeout(self):
        try:
            try:
                raise asyncio.CancelledError()
            except asyncio.CancelledError:
                raise TimeoutError() from None
        except TimeoutError as error:
            timeout = error

        self.assertIs(cctv_logging.root_cause(timeout), timeout)
        (line,) = self._log(timeout)
        self.assertTrue(line.startswith("WARNING:"))


if __name__ == "__main__":
    unittest.main()
