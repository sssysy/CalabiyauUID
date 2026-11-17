from gsuid_core.utils.plugins_config.gs_config import StringConfig

from .config_default import CONFIG_DEFAULT
from ..utils.utils.paths import CONFIG_PATH

CalabiyauConfig = StringConfig(
    "CalabiyauUID",
    CONFIG_PATH,
    CONFIG_DEFAULT,
)
