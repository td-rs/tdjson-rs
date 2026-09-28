# Python bindings for TDLib's JSON interface, backed by the td-rs Rust
# implementation compiled directly into the extension module.
from .tdjson_ext import td_create_client_id, td_send, td_receive, td_execute
from ._version import __version__, __copyright__, __license__

__all__ = [
    "td_create_client_id",
    "td_send",
    "td_receive",
    "td_execute",
    "__version__",
    "__copyright__",
    "__license__",
]
