"""PDF 回退链获取器

按照五级降级策略尝试获取论文 PDF:
1. 直接使用 paper.pdf_url（来自数据源/出版商 OA 链接）
2. Unpaywall API 通过 DOI 查找 OA 版本
3. CORE API 全文搜索
4. arXiv 同标题预印本搜索
5. 全部失败 → 返回 None 并记录日志

用法::

    from souwen.paper import fetch_pdf

    pdf_path = await fetch_pdf(paper, save_dir=Path("./pdfs"))
"""

from __future__ import annotations

import logging
from pathlib import Path

from souwen.exceptions import ConfigError, NotFoundError
from souwen.http_client import SouWenHttpClient
from souwen.models import PaperResult

logger = logging.getLogger(__name__)

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
    # 移除常见非法字符
    safe = title.replace("/", "_").replace("\\", "_").replace(":", "_")
    safe = safe.replace('"', "").replace("'", "").replace("?", "")
    safe = safe.replace("<", "").replace(">", "").replace("|", "")
    safe = safe.replace("\n", " ").replace("\r", "").strip()
    # 截断
    if len(safe) > max_len:
        safe = safe[:max_len].rstrip()
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
    try:
        resp = await client.get(url, follow_redirects=True)

        if resp.status_code != 200:
            logger.warning("PDF 下载失败 (HTTP %d): %s", resp.status_code, url)
            return None

        content = resp.content
        if len(content) > _MAX_PDF_SIZE:
            logger.warning("PDF 文件过大 (%d bytes)，已跳过: %s", len(content), url)
            return None

        # 基本 PDF 格式校验
        if not content[:5].startswith(b"%PDF-"):
            logger.warning("下载内容非 PDF 格式: %s", url)
            return None

        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(content)
        logger.info("PDF 已保存: %s", save_path)
        return save_path

    except Exception as exc:
        logger.warning("PDF 下载异常: %s - %s", url, exc)
        return None


async def _try_direct_link(
    paper: PaperResult,
    save_path: Path,
    client: SouWenHttpClient,
) -> Path | None:
    """策略 1: 使用论文自带的 PDF 链接。"""
    if not paper.pdf_url:
        return None
    logger.debug("尝试直接 PDF 链接: %s", paper.pdf_url)
    return await _download_pdf(paper.pdf_url, save_path, client)


async def _try_unpaywall(
    paper: PaperResult,
    save_path: Path,
    client: SouWenHttpClient,
) -> Path | None:
    """策略 2: 通过 Unpaywall 查找 OA PDF。"""
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
        logger.debug("Unpaywall 未配置邮箱，跳过")
    except NotFoundError:
        logger.debug("Unpaywall 未找到 DOI: %s", paper.doi)
    except Exception as exc:
        logger.warning("Unpaywall 查找失败: %s", exc)

    return None


async def _try_core(
    paper: PaperResult,
    save_path: Path,
    client: SouWenHttpClient,
) -> Path | None:
    """策略 3: 通过 CORE 搜索全文 PDF。"""
    if not paper.title:
        return None

    try:
        from souwen.paper.core import CoreClient

        async with CoreClient() as core:
            search_result = await core.search(paper.title, limit=3)
            for result in search_result.results:
                if result.pdf_url:
                    logger.debug("CORE 找到全文 PDF: %s", result.pdf_url)
                    downloaded = await _download_pdf(
                        result.pdf_url, save_path, client
                    )
                    if downloaded:
                        return downloaded
    except ConfigError:
        logger.debug("CORE API Key 未配置，跳过")
    except Exception as exc:
        logger.warning("CORE 搜索失败: %s", exc)

    return None


async def _try_arxiv(
    paper: PaperResult,
    save_path: Path,
    client: SouWenHttpClient,
) -> Path | None:
    """策略 4: 在 arXiv 搜索同标题预印本。"""
    if not paper.title:
        return None

    try:
        from souwen.paper.arxiv import ArxivClient

        async with ArxivClient() as arxiv:
            # 用标题精确搜索
            query = f'ti:"{paper.title}"'
            search_result = await arxiv.search(query, max_results=3)
            for result in search_result.results:
                if result.pdf_url:
                    logger.debug("arXiv 找到预印本 PDF: %s", result.pdf_url)
                    downloaded = await _download_pdf(
                        result.pdf_url, save_path, client
                    )
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

    filename = _safe_filename(paper.title) + ".pdf"
    save_path = save_dir / filename

    # 如果文件已存在，直接返回
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
