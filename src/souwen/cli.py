"""``souwen`` 命令行：``mcp`` | ``serve`` | ``doctor``（SPEC 2.4）。

- ``souwen mcp``：以 stdio 启动 MCP server，供 Agent 宿主以本地进程方式接入。
- ``souwen serve``：启动 HTTP API（含 ``/mcp`` streamable HTTP）。
- ``souwen doctor``：本地诊断（配置加载、runtime 构建、源可用性统计）；
  ``--live`` 的按出口级别体检在 P3 提供。
"""

from __future__ import annotations

import argparse
import sys


def _cmd_mcp(args: argparse.Namespace) -> int:
    from souwen.agent import AgentRuntime, get_agent_runtime
    from souwen.server.mcp_server import build_mcp_server

    runtime: AgentRuntime = get_agent_runtime()
    server = build_mcp_server(runtime)
    server.run()  # stdio
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import os

    import uvicorn

    uvicorn.run(
        "souwen.server.app:app",
        host=args.host,
        port=args.port or int(os.environ.get("PORT", "8000")),
        workers=1,
        log_level="info",
        timeout_keep_alive=120,
    )
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    from souwen.config import get_config
    from souwen.server.v2_runtime import build_target_runtime

    config = get_config()
    runtime = build_target_runtime(config)
    try:
        available = 0
        unavailable = 0
        by_reason: dict[str, int] = {}
        for item in runtime.services.provider_items:
            if item.availability == "available":
                available += 1
            else:
                unavailable += 1
            by_reason[item.reason] = by_reason.get(item.reason, 0) + 1
        print(
            f"souwen doctor: runtime built, providers available={available} unavailable={unavailable}"
        )
        for reason, count in sorted(by_reason.items()):
            print(f"  {reason}: {count}")
        warp = "enabled" if config.warp_enabled else "disabled"
        user_password = "set" if config.effective_user_password else "open"
        print(f"  warp: {warp}; user auth: {user_password}")
        return 0
    finally:
        import asyncio

        asyncio.run(runtime.close())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="souwen",
        description="SouWen: free search & fetch for agents (MCP + HTTP)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    mcp = sub.add_parser("mcp", help="run the MCP server over stdio")
    mcp.set_defaults(func=_cmd_mcp)

    serve = sub.add_parser("serve", help="run the HTTP API server")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=None, help="default: $PORT or 8000")
    serve.set_defaults(func=_cmd_serve)

    doctor = sub.add_parser("doctor", help="diagnose the local runtime")
    doctor.set_defaults(func=_cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
