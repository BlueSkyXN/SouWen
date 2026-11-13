"""SouWen: free search and fetch for AI agents."""

__version__ = "3.0.0a1"

# __version__ must exist before agent -> server.v2_runtime imports it back.
from souwen.agent import fetch, get_agent_runtime, search  # noqa: E402

__all__ = ["__version__", "fetch", "get_agent_runtime", "search"]
