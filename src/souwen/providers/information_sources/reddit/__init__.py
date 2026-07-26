"""Built-in reddit Provider v2 package."""

from .adapter import RedditClientProtocol, RedditSearchProvider
from .manifest import REDDIT_PROVIDER_MANIFEST
from .spec import REDDIT_PROVIDER_SPEC

__all__ = [
    "REDDIT_PROVIDER_MANIFEST",
    "REDDIT_PROVIDER_SPEC",
    "RedditClientProtocol",
    "RedditSearchProvider",
]
