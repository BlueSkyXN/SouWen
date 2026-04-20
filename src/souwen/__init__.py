"""SouWen - 面向 AI Agent 的学术论文 + 专利 + 网页信息统一获取工具库"""

__version__ = "0.7.3"

from souwen.search import search, search_papers, search_patents
from souwen.web.search import web_search
from souwen.config import get_config, reload_config

__all__ = [
    "search",
    "search_papers",
    "search_patents",
    "web_search",
    "get_config",
    "reload_config",
    "__version__",
]
