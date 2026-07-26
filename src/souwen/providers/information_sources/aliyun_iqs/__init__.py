"""Built-in aliyun_iqs Provider v2 package."""

from .adapter import AliyunIQSClientProtocol, AliyunIQSSearchProvider
from .manifest import ALIYUN_IQS_PROVIDER_MANIFEST
from .spec import ALIYUN_IQS_PROVIDER_SPEC

__all__ = [
    "ALIYUN_IQS_PROVIDER_MANIFEST",
    "ALIYUN_IQS_PROVIDER_SPEC",
    "AliyunIQSClientProtocol",
    "AliyunIQSSearchProvider",
]
