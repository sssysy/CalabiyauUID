"""init"""

from gsuid_core.sv import Plugins

from .utils.helper import resource_sync  # noqa: F401

Plugins(
    name="CalabiyauUID",
    force_prefix=["kq"],
    allow_empty_prefix=False,
)
