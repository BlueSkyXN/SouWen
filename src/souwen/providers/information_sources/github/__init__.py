"""Built-in github Provider v2 package."""

from .adapter import GitHubClientProtocol, GitHubSearchProvider
from .manifest import GITHUB_PROVIDER_MANIFEST
from .spec import GITHUB_PROVIDER_SPEC

__all__ = [
    "GITHUB_PROVIDER_MANIFEST",
    "GITHUB_PROVIDER_SPEC",
    "GitHubClientProtocol",
    "GitHubSearchProvider",
]
