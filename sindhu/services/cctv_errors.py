"""CCTV error types, kept free of provider imports so any layer can use them."""

from __future__ import annotations

import re


class SourceError(RuntimeError):
    """Safe, stable source failure.

    The exception intentionally contains only a machine-readable code.  In
    particular, provider URLs, query strings, response bodies, and transport
    exception strings must not become observable application output.
    """

    def __init__(self, code: str):
        safe_code = code if re.fullmatch(r"[a-z0-9_]+", str(code)) else "source_error"
        self.code = safe_code
        super().__init__(safe_code)


__all__ = ["SourceError"]
