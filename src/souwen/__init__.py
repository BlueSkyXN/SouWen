"""SouWen target SDK package."""

__version__ = "2.0.0rc5"

from souwen.delivery.client_sdk import AsyncSouWenClient, SouWenClient

__all__ = [
    "SouWenClient",
    "AsyncSouWenClient",
    "__version__",
]
