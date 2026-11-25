"""The only place that knows which sources exist."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping

from sindhu.services.cctv_providers.base import CctvProvider
from sindhu.services.cctv_providers.dwr import DwrProvider
from sindhu.services.cctv_providers.hatyai import HatyaiProvider
from sindhu.services.cctv_providers.rid import RidProvider
from sindhu.services.cctv_providers.transport import Transport

PROVIDER_CLASSES: tuple[type[CctvProvider], ...] = (
    HatyaiProvider,
    DwrProvider,
    RidProvider,
)
PROVIDER_BY_SOURCE: dict[str, type[CctvProvider]] = {
    provider.source: provider for provider in PROVIDER_CLASSES
}
SOURCES: tuple[str, ...] = tuple(PROVIDER_BY_SOURCE)


def build_providers(
    transport: Transport,
    now: Callable[[], dt.datetime],
    base_urls: Mapping[str, str],
) -> dict[str, CctvProvider]:
    return {
        source: provider(transport, base_url=base_urls[source], now=now)
        for source, provider in PROVIDER_BY_SOURCE.items()
    }
