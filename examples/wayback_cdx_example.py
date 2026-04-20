"""Wayback Machine CDX Server API 使用示例

展示如何使用 WaybackClient.query_snapshots() 方法查询历史快照列表。
"""

import asyncio

from souwen.web.wayback import WaybackClient


async def main():
    """演示 CDX API 的各种用法"""

    async with WaybackClient() as client:
        print("=" * 60)
        print("示例 1: 查询网站的所有历史快照")
        print("=" * 60)

        # 查询 example.com 的历史快照
        resp = await client.query_snapshots(
            url="example.com",
            limit=10,  # 限制只返回 10 条
        )

        if resp.error:
            print(f"查询失败: {resp.error}")
        else:
            print(f"找到 {resp.total} 个快照 (显示前 10 个):\n")
            for i, snapshot in enumerate(resp.snapshots[:10], 1):
                print(f"{i}. {snapshot.published_date} - {snapshot.status_code}")
                print(f"   URL: {snapshot.archive_url}")
                print(f"   类型: {snapshot.mime_type}, 大小: {snapshot.length} 字节\n")

        print("\n" + "=" * 60)
        print("示例 2: 查询特定日期范围的快照（2023 年）")
        print("=" * 60)

        resp = await client.query_snapshots(
            url="example.com",
            from_date="20230101",
            to_date="20231231",
            limit=5,
        )

        if not resp.error:
            print(f"2023 年共有 {resp.total} 个快照 (显示前 5 个):\n")
            for snapshot in resp.snapshots[:5]:
                print(f"- {snapshot.published_date}: {snapshot.archive_url}")

        print("\n" + "=" * 60)
        print("示例 3: 只查询成功的 HTML 页面")
        print("=" * 60)

        resp = await client.query_snapshots(
            url="example.com",
            filter_status=[200],  # 只要 HTTP 200
            filter_mime="text/html",  # 只要 HTML
            limit=5,
        )

        if not resp.error:
            print(f"找到 {resp.total} 个成功的 HTML 快照 (显示前 5 个):\n")
            for snapshot in resp.snapshots[:5]:
                print(f"- {snapshot.published_date}: {snapshot.mime_type} ({snapshot.length} 字节)")

        print("\n" + "=" * 60)
        print("示例 4: 按天去重，每天只保留一个快照")
        print("=" * 60)

        resp = await client.query_snapshots(
            url="example.com",
            collapse="timestamp:8",  # timestamp 的前 8 位（YYYYMMDD）去重
            limit=10,
        )

        if not resp.error:
            print(f"去重后有 {resp.total} 个快照 (显示前 10 个):\n")
            for snapshot in resp.snapshots[:10]:
                print(f"- {snapshot.published_date}: {snapshot.archive_url}")

        print("\n" + "=" * 60)
        print("示例 5: 使用通配符查询整个域名")
        print("=" * 60)

        # 查询 example.com 及其所有子路径
        resp = await client.query_snapshots(
            url="example.com/*",  # * 匹配所有路径
            limit=10,
        )

        if not resp.error:
            print(f"域名下共有 {resp.total} 个 URL 被存档 (显示前 10 个):\n")
            for snapshot in resp.snapshots[:10]:
                print(f"- {snapshot.url}")
                print(f"  快照: {snapshot.archive_url}\n")


if __name__ == "__main__":
    asyncio.run(main())
