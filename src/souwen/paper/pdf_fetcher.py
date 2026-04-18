"""PDF 回退链获取器

按照五级降级策略尝试获取论文 PDF:
    1. 直接使用 paper.pdf_url（来自数据源/出版商 OA 链接）
    2. Unpaywall API 通过 DOI 查找 OA 版本
    3. CORE API 全文搜索
    4. arXiv 同标题预印本搜索
    5. 全部失败 → 返回 None 并记录日志

文件用途：提供多源 PDF 获取的降级策略，提高论文全文检索成功率。

函数/类清单：
    _safe_filename(title: str, max_len: int = 80) -> str
        - 功能：从论文标题生成安全的文件系统文件名
        - 输入：title 论文标题, max_len 文件名最大字符数
        - 输出：清理后的安全文件名（不含扩展名）
        - 处理：去除常见非法字符（/\:\"'?<>|）

    _download_pdf(url: str, save_path: Path, client: SouWenHttpClient) -> Path|None
        - 功能：下载 PDF 文件并保存到磁盘
        - 输入：url PDF 下载链接, save_path 本地保存路径, client HTTP 客户端
        - 输出：成功返回文件路径，失败返回 None
        - 校验：检查 HTTP 状态码、文件大小（最大 100MB）、PDF 魔数

    _try_direct_link(paper: PaperResult, save_path: Path, client) -> Path|None
        - 功能：策略 1：使用论文自带的 PDF 链接

    _try_unpaywall(paper: PaperResult, save_path: Path, client) -> Path|None
        - 功能：策略 2：通过 Unpaywall 查找 OA PDF

    _try_core(paper: PaperResult, save_path: Path, client) -> Path|None
        - 功能：策略 3：通过 CORE 搜索全文 PDF

    _try_arxiv(paper: PaperResult, save_path: Path, client) -> Path|None
        - 功能：策略 4：在 arXiv 搜索同标题预印本

    fetch_pdf(paper: PaperResult, save_dir: Path|None = None) -> Path|None
        - 功能：五级降级策略获取论文 PDF
        - 输入：paper 论文模型（需至少含 title/doi/pdf_url 之一），save_dir 保存目录
        - 输出：成功返回 PDF 文件路径，全部失败返回 None
        - 缓存：若文件已存在，直接返回无需重新下载

用法::

    from souwen.paper import fetch_pdf

    pdf_path = await fetch_pdf(paper, save_dir=Path("./pdfs"))

模块依赖：
    - SouWenHttpClient: 统一 HTTP 客户端
    - UnpaywallClient, CoreClient, ArxivClient: 各数据源客户端
"""

from __future__ import annotations

import ipaddress
import asyncio
import logging
from pathlib import Path
from urllib.parse import urlparse

import httpx

from souwen.exceptions import ConfigError, NotFoundError
from souwen.http_client import SouWenHttpClient
from souwen.models import PaperResult

logger = logging.getLogger(__name__)


_BLOCKED_HOSTNAMES = frozenset({
    "localhost", "localhost.localdomain", "localhost4", "localhost6",
})

# 仅阻止真正危险的 SSRF 目标网段（避免 is_private 在 Python 3.11+ 误拦 198.18.0.0/15 等）
_SSRF_BLOCKED_NETS = tuple(
    ipaddress.ip_network(n) for n in (
        "0.0.0.0/8",        # "This host"
        "10.0.0.0/8",       # RFC 1918
        "100.64.0.0/10",    # Carrier-grade NAT
        "127.0.0.0/8",      # Loopback
        "169.254.0.0/16",   # Link-local / 云元数据
        "172.16.0.0/12",    # RFC 1918
        "192.0.0.0/24",     # IETF Protocol
        "192.168.0.0/16",   # RFC 1918
        "::1/128",          # IPv6 loopback
        "fc00::/7",         # IPv6 ULA
        "fe80::/10",        # IPv6 link-local
    )
)


def _is_safe_url(url: str) -> bool:
    """检查 URL 是否安全（防止 SSRF）

    阻止策略：
    1. 仅允许 http/https
    2. 拒绝 localhost 等已知本地主机名
    3. DNS 解析主机名，检查所有解析结果是否命中 SSRF 危险网段
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    hostname = parsed.hostname
    if not hostname:
        return False
    if hostname.lower() in _BLOCKED_HOSTNAMES:
        return False
    try:
        import socket
        addrinfos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
        for _family, _type, _proto, _canon, sockaddr in addrinfos:
            ip = ipaddress.ip_address(sockaddr[0])
            if any(ip in net for net in _SSRF_BLOCKED_NETS):
                return False
    except (socket.gaierror, OSError, ValueError):
        return False  # 无法解析的主机名拒绝访问
    return True

# PDF 最大下载大小 (100 MB)
_MAX_PDF_SIZE = 100 * 1024 * 1024


def _safe_filename(title: str, max_len: int = 80) -> str:
    """从论文标题生成安全文件名。

    Args:
        title: 论文标题。
        max_len: 文件名最大字符数。

    Returns:
        清理后的安全文件名（不含扩展名）。
    """
    # 移除常见非法字符（操作系统不允许的字符）
    safe = title.replace("/", "_").replace("\\", "_").replace(":", "_")
    safe = safe.replace('"', "").replace("'", "").replace("?", "")
    safe = safe.replace("<", "").replace(">", "").replace("|", "")
    safe = safe.replace("\n", " ").replace("\r", "").strip()
    # 截断至最大长度
    if len(safe) > max_len:
        safe = safe[:max_len].rstrip()
    # 若标题全为非法字符而被清空，使用默认名称
    return safe or "untitled"


async def _download_pdf(
    url: str,
    save_path: Path,
    client: SouWenHttpClient,
) -> Path | None:
    """下载 PDF 文件并保存。

    Args:
        url: PDF 下载链接。
        save_path: 保存路径。
        client: HTTP 客户端实例。

    Returns:
        成功返回文件路径，失败返回 None。
    """
    if not _is_safe_url(url):
        logger.warning("PDF URL 不安全，已拒绝: %s", url)
        return None

    try:
        resp = await client.get(url)

        # 检查 HTTP 状态码
        if resp.status_code != 200:
            logger.warning("PDF 下载失败 (HTTP %d): %s", resp.status_code, url)
            return None

        content = resp.content
        # 检查文件大小是否超过限制（防止恶意或损坏的文件）
        if len(content) > _MAX_PDF_SIZE:
            logger.warning("PDF 文件过大 (%d bytes)，已跳过: %s", len(content), url)
            return None

        # 基本 PDF 格式校验：检查 PDF 魔数（%PDF-）
        # 在前 1024 字节内查找，兼容带 BOM 或其他头部信息的 PDF
        if b"%PDF-" not in content[:1024]:
            logger.warning("下载内容非 PDF 格式: %s", url)
            return None

        # 创建目录（若不存在）并保存文件（使用线程池避免阻塞事件循环）
        await asyncio.to_thread(save_path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(save_path.write_bytes, content)
        logger.info("PDF 已保存: %s", save_path)
        return save_path

    except (httpx.HTTPError, IOError, OSError) as exc:
        logger.warning("PDF 下载异常: %s - %s", url, exc)
        return None


async def _try_direct_link(
    paper: PaperResult,
    save_path: Path,
    client: SouWenHttpClient,
) -> Path | None:
    """策略 1: 使用论文自带的 PDF 链接。

    优先尝试使用从数据源直接获取的 PDF 链接（通常来自出版商或 OA 仓库）。
    """
    if not paper.pdf_url:
        return None
    logger.debug("尝试直接 PDF 链接: %s", paper.pdf_url)
    return await _download_pdf(paper.pdf_url, save_path, client)


async def _try_unpaywall(
    paper: PaperResult,
    save_path: Path,
    client: SouWenHttpClient,
) -> Path | None:
    """策略 2: 通过 Unpaywall 查找 OA PDF。

    使用论文 DOI 查询 Unpaywall 数据库，查找合法的开放获取 PDF 版本。
    """
    if not paper.doi:
        return None

    try:
        from souwen.paper.unpaywall import UnpaywallClient

        async with UnpaywallClient() as unpaywall:
            result = await unpaywall.find_oa(paper.doi)
            if result.pdf_url:
                logger.debug("Unpaywall 找到 OA PDF: %s", result.pdf_url)
                return await _download_pdf(result.pdf_url, save_path, client)
    except ConfigError:
        # Unpaywall 邮箱未配置，跳过此策略
        logger.debug("Unpaywall 未配置邮箱，跳过")
    except NotFoundError:
        # DOI 在 Unpaywall 中未找到或无 OA 版本
        logger.debug("Unpaywall 未找到 DOI: %s", paper.doi)
    except Exception as exc:
        logger.warning("Unpaywall 查找失败: %s", exc)

    return None


async def _try_core(
    paper: PaperResult,
    save_path: Path,
    client: SouWenHttpClient,
) -> Path | None:
    """策略 3: 通过 CORE 搜索全文 PDF。

    使用论文标题搜索 CORE 文献库，查找相关论文的全文 PDF（前 3 个结果）。
    """
    if not paper.title:
        return None

    try:
        from souwen.paper.core import CoreClient

        async with CoreClient() as core:
            # 按标题搜索，限制前 3 个结果以加快速度
            search_result = await core.search(paper.title, limit=3)
            for result in search_result.results:
                if result.pdf_url:
                    logger.debug("CORE 找到全文 PDF: %s", result.pdf_url)
                    downloaded = await _download_pdf(result.pdf_url, save_path, client)
                    if downloaded:
                        return downloaded
    except ConfigError:
        # CORE API Key 未配置，跳过此策略
        logger.debug("CORE API Key 未配置，跳过")
    except Exception as exc:
        logger.warning("CORE 搜索失败: %s", exc)

    return None


async def _try_arxiv(
    paper: PaperResult,
    save_path: Path,
    client: SouWenHttpClient,
) -> Path | None:
    """策略 4: 在 arXiv 搜索同标题预印本。

    使用论文标题在 arXiv 中精确搜索（title 字段），查找相同标题的预印本版本
    （arXiv 论文均可获取 PDF）。
    """
    if not paper.title:
        return None

    try:
        from souwen.paper.arxiv import ArxivClient

        async with ArxivClient() as arxiv:
            # 用标题字段精确搜索（ti: 前缀），限制前 3 个结果
            query = f'ti:"{paper.title}"'
            search_result = await arxiv.search(query, max_results=3)
            for result in search_result.results:
                if result.pdf_url:
                    logger.debug("arXiv 找到预印本 PDF: %s", result.pdf_url)
                    downloaded = await _download_pdf(result.pdf_url, save_path, client)
                    if downloaded:
                        return downloaded
    except Exception as exc:
        logger.warning("arXiv 搜索失败: %s", exc)

    return None


async def fetch_pdf(
    paper: PaperResult,
    save_dir: Path | None = None,
) -> Path | None:
    """五级降级策略获取论文 PDF。

    按以下优先级逐级尝试获取 PDF:
        1. 论文自带的 pdf_url（出版商/数据源 OA 链接）
        2. Unpaywall 通过 DOI 查找 OA 版本
        3. CORE 全文搜索
        4. arXiv 同标题预印本
        5. 全部失败 → 返回 None

    Args:
        paper: 论文信息模型，至少需要 title、doi、pdf_url 中的一个。
        save_dir: PDF 保存目录。默认为当前目录下的 ``pdfs/``。

    Returns:
        成功返回 PDF 文件路径，全部失败返回 None。
    """
    if save_dir is None:
        save_dir = Path("pdfs")

    # 从论文标题生成文件名
    filename = _safe_filename(paper.title) + ".pdf"
    save_path = save_dir / filename

    # 若文件已存在，无需重新下载
    if save_path.exists():
        logger.info("PDF 已存在，跳过下载: %s", save_path)
        return save_path

    logger.info(
        "开始获取 PDF: %s (DOI: %s)",
        paper.title[:60],
        paper.doi or "无",
    )

    async with SouWenHttpClient() as client:
        # 策略 1: 直接链接
        result = await _try_direct_link(paper, save_path, client)
        if result:
            return result

        # 策略 2: Unpaywall
        result = await _try_unpaywall(paper, save_path, client)
        if result:
            return result

        # 策略 3: CORE
        result = await _try_core(paper, save_path, client)
        if result:
            return result

        # 策略 4: arXiv
        result = await _try_arxiv(paper, save_path, client)
        if result:
            return result

    # 策略 5: 全部失败
    logger.warning(
        "PDF 获取失败（五级策略均未命中）: %s (DOI: %s)",
        paper.title[:60],
        paper.doi or "无",
    )
    return None
