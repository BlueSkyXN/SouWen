"""Research-output clients and normalized non-paper research records."""

from souwen.providers.runtime_clients.research_output.datacite import DataCiteClient
from souwen.providers.runtime_clients.research_output.figshare import FigshareClient

__all__ = ["DataCiteClient", "FigshareClient"]
