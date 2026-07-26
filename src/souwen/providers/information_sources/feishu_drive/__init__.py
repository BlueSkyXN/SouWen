"""Built-in feishu_drive Provider v2 package."""

from .adapter import FeishuDriveClientProtocol, FeishuDriveSearchProvider
from .manifest import FEISHU_DRIVE_PROVIDER_MANIFEST
from .spec import FEISHU_DRIVE_PROVIDER_SPEC

__all__ = [
    "FEISHU_DRIVE_PROVIDER_MANIFEST",
    "FEISHU_DRIVE_PROVIDER_SPEC",
    "FeishuDriveClientProtocol",
    "FeishuDriveSearchProvider",
]
