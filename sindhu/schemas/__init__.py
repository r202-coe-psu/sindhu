"""Schema modules, resolved on first use.

Nothing is imported eagerly: each `sindhu.models` module needs exactly one
schema module, so importing them all made every model drag in every schema.
Attribute access still resolves, so `from sindhu import schemas` followed by
`schemas.stations.Station` keeps working for the API layer.
"""

import importlib

__all__ = [
    "bases",
    "metrics",
    "stations",
    "system_settings",
    "tokens",
    "users",
    "visual_feeds",
    "zones",
]


def __getattr__(name):
    if name in __all__:
        module = importlib.import_module(f".{name}", __name__)
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(__all__)
