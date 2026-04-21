"""knowledge/ — 百科/知识库域（v1）

DeepWiki 归 fetch（D2），不在这里；知识库域目前只有 Wikipedia。
"""

from souwen.web.wikipedia import WikipediaClient

__all__ = ["WikipediaClient"]
