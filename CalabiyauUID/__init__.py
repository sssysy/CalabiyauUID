"""init"""

from gsuid_core.sv import Plugins

from .utils.helper import (
    cache_manager,  # noqa: F401
    resource_sync,  # noqa: F401
)
from .utils.helper.backup_hints import register_calabiyau_backup_hints

Plugins(
    name="CalabiyauUID",
    force_prefix=["kq"],
    allow_empty_prefix=False,
)

register_calabiyau_backup_hints()
