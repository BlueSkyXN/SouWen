"""integrations/mcp/ — MCP (Model Context Protocol) 集成（v1）

子模块：
  - server —— MCP server 入口
  - tools/ —— 具体工具实现（按 domain 拆分）
    - tools.bilibili —— Bilibili 相关 MCP 工具
"""

from souwen.integrations.mcp.server import *  # noqa: F401,F403
