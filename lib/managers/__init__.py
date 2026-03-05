"""Manager package for incremental cmd_manager modularization."""

from .util import get_user_selection
from .base import BaseManager, CommandResult, DEFAULT_MOUNT_PATH
from .local import LocalManager
from .remote import SSHManager
from .image import BaseImageManager, ImageFileManager, SDCardManager
from .factory import create_manager, interactive_create_manager

__all__ = [
    'get_user_selection',
    'BaseManager',
    'CommandResult',
    'DEFAULT_MOUNT_PATH',
    'LocalManager',
    'SSHManager',
    'BaseImageManager',
    'ImageFileManager',
    'SDCardManager',
    'create_manager',
    'interactive_create_manager',
]
