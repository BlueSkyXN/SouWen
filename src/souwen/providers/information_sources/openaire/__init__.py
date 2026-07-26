"""Built-in OpenAIRE Provider v2 package."""

from .adapter import OpenAireClientProtocol, OpenAireSearchProvider
from .manifest import OPENAIRE_PROVIDER_MANIFEST
from .spec import OPENAIRE_PROVIDER_SPEC

__all__ = [
    "OPENAIRE_PROVIDER_MANIFEST",
    "OPENAIRE_PROVIDER_SPEC",
    "OpenAireClientProtocol",
    "OpenAireSearchProvider",
]
