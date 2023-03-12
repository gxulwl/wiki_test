from wiki.functions.versions import get_version

default_app_config = "wiki.apps.WikiConfig"

VERSION = (0, 9, 0, "final", 0)
__version__ = get_version(VERSION)