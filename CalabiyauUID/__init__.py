"""init"""

from gsuid_core.sv import Plugins

from .utils.helper import (
    cache_manager,  # noqa: F401
    resource_sync,  # noqa: F401
)
from .utils.plugin_status import register_calabiyau_status
from .utils.helper.backup_hints import register_calabiyau_backup_hints

Plugins(
    name="CalabiyauUID",
    force_prefix=["kq"],
    allow_empty_prefix=False,
)

register_calabiyau_backup_hints()
register_calabiyau_status()
