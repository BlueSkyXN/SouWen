"""浏览器指纹管理

文件用途：
    提供真实浏览器请求头和 TLS 指纹模拟，用于突破反爬检测（JA3、UA、Sec-CH-UA 等）。
    支持多个浏览器版本和操作系统组合，增加指纹多样性。

函数/类清单：
    BrowserFingerprint（类）
        - 功能：单次请求的浏览器指纹生成器
        - 方法：
          * __init__(chrome_version: dict|None) — 初始化指纹，可指定浏览器版本
          * user_agent (property) → str — 返回完整 User-Agent 字符串
          * impersonate (property) → str — 返回 curl_cffi impersonate 参数（TLS 指纹）
          * headers (property) → dict[str,str] — 返回完整浏览器请求头（含 Sec-CH-UA 系列）
          * rotate() → BrowserFingerprint — 轮换到新的指纹实例

    get_default_fingerprint() -> BrowserFingerprint
        - 功能：获取确定的默认指纹（Chrome 最新版本）
        - 用途：需要稳定指纹时使用

    get_random_fingerprint() -> BrowserFingerprint
        - 功能：获取随机指纹，支持多浏览器/操作系统组合
        - 用途：模拟不同客户端，提高反爬规避能力

    get_api_headers(email=None, api_key=None, bearer_token=None) -> dict[str, str]
        - 功能：[已修正] 构造 API 调用（非爬虫场景）的请求头，使用规范的 SouWen UA
        - 入参：email → From 头；api_key → X-API-Key；bearer_token → Authorization: Bearer

关键变量：
    _CHROME_VERSIONS: list[dict]
        - 浏览器版本库，包含 Chrome/Edge/Safari 版本
        - 关键字段：version (版本号), ua (User-Agent 字符串),
                   sec_ch_ua (Sec-CH-UA 头值), impersonate (curl_cffi 指纹)
        - 注意：curl_cffi 最高仅支持 chrome124 的 TLS 指纹，UA 用新版无碍

    _PLATFORMS: list[dict]
        - 操作系统指纹库（与 Chrome 版本随机组合）
        - 关键字段：platform (Sec-CH-UA-Platform 值), ua_os (User-Agent 中的 OS 部分)

模块依赖：
    - random: 随机选择浏览器和操作系统
    - souwen.__version__: SouWen API User-Agent 构建
"""

from __future__ import annotations

import random

from souwen import __version__

# Chrome / Edge / Safari 浏览器指纹库（定期更新）
# 注意：curl_cffi 最高仅支持 chrome124 的 TLS 指纹，UA 用新版无碍
_CHROME_VERSIONS = [
    {
        "version": "146",
        "ua": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/146.0.0.0 Safari/537.36"
        ),
        "sec_ch_ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
        "impersonate": "chrome124",
    },
    {
        "version": "137",
        "ua": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/137.0.0.0 Safari/537.36"
        ),
        "sec_ch_ua": '"Chromium";v="137", "Not-A.Brand";v="24", "Google Chrome";v="137"',
        "impersonate": "chrome124",
    },
    {
        "version": "136",
        "ua": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/136.0.0.0 Safari/537.36"
        ),
        "sec_ch_ua": '"Chromium";v="136", "Not-A.Brand";v="24", "Google Chrome";v="136"',
        "impersonate": "chrome124",
    },
    {
        "version": "135",
        "ua": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/135.0.0.0 Safari/537.36"
        ),
        "sec_ch_ua": '"Chromium";v="135", "Not-A.Brand";v="24", "Google Chrome";v="135"',
        "impersonate": "chrome124",
    },
    {
        "version": "133",
        "ua": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/133.0.0.0 Safari/537.36"
        ),
        "sec_ch_ua": '"Chromium";v="133", "Not-A.Brand";v="24", "Google Chrome";v="133"',
        "impersonate": "chrome124",
    },
    {
        "version": "131",
        "ua": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "sec_ch_ua": '"Chromium";v="131", "Not-A.Brand";v="24", "Google Chrome";v="131"',
        "impersonate": "chrome124",
    },
    {
        "version": "125",
        "ua": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "sec_ch_ua": '"Chromium";v="125", "Not-A.Brand";v="24", "Google Chrome";v="125"',
        "impersonate": "chrome120",
    },
    {
        "version": "124",
        "ua": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "sec_ch_ua": '"Chromium";v="124", "Not-A.Brand";v="24", "Google Chrome";v="124"',
        "impersonate": "chrome120",
    },
    # Edge (Chromium-based) — 同样复用 chrome124 TLS 指纹
    {
        "version": "edge137",
        "ua": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0"
        ),
        "sec_ch_ua": '"Chromium";v="137", "Not-A.Brand";v="24", "Microsoft Edge";v="137"',
        "impersonate": "chrome124",
    },
    # Safari (macOS) — impersonate 使用 safari 系列
    {
        "version": "safari17",
        "ua": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.5 Safari/605.1.15"
        ),
        "sec_ch_ua": "",
        "impersonate": "safari17_0",
    },
]

# 操作系统指纹（与 Chrome 版本随机组合，增加指纹多样性）
# 注意：Windows 11 实际仍报告 "Windows NT 10.0"，此处保持一致
_PLATFORMS = [
    {"platform": '"Windows"', "ua_os": "Windows NT 10.0; Win64; x64"},
    {"platform": '"macOS"', "ua_os": "Macintosh; Intel Mac OS X 10_15_7"},
    {"platform": '"Linux"', "ua_os": "X11; Linux x86_64"},
    {"platform": '"Android"', "ua_os": "Linux; Android 14; Pixel 8"},
]


class BrowserFingerprint:
    """浏览器指纹生成器

    为单次请求生成一致的浏览器指纹（UA + Sec-CH-UA + TLS impersonate），
    确保请求在网络层和应用层看起来像真实浏览器。

    属性：
        _chrome: 所选浏览器版本信息（包含 ua、sec_ch_ua、impersonate）
        _platform: 所选操作系统指纹
    """

    def __init__(self, chrome_version: dict | None = None):
        """初始化浏览器指纹

        Args:
            chrome_version: 指定浏览器版本字典；None 则随机选择
        """
        self._chrome = chrome_version or random.choice(_CHROME_VERSIONS)
        self._platform = random.choice(_PLATFORMS)

    @property
    def user_agent(self) -> str:
        """完整 User-Agent 字符串（浏览器身份标识）"""
        return self._chrome["ua"]

    @property
    def impersonate(self) -> str:
        """curl_cffi impersonate 参数（TLS 指纹模拟）

        用于 curl_cffi 的 impersonate 参数，实现 JA3 指纹伪装。
        """
        return self._chrome["impersonate"]

    @property
    def headers(self) -> dict[str, str]:
        """完整的浏览器请求头（含 Sec-CH-UA 系列）

        包括：
        - User-Agent: 浏览器标识
        - sec-ch-ua*: 客户端提示 (Client Hints) 系列请求头
        - Accept*: 内容协商头
        - Sec-Fetch-*: 获取元数据头（防 CSRF 检测）
        - Connection: 连接策略

        Returns:
            浏览器标准请求头字典
        """
        return {
            "User-Agent": self._chrome["ua"],
            "sec-ch-ua": self._chrome["sec_ch_ua"],
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": self._platform["platform"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }

    def rotate(self) -> "BrowserFingerprint":
        """轮换到新的指纹（重新随机选择浏览器和操作系统）

        Returns:
            新的 BrowserFingerprint 实例
        """
        return BrowserFingerprint()


def get_default_fingerprint() -> BrowserFingerprint:
    """获取确定的默认浏览器指纹

    使用预定义的第一个浏览器版本（Chrome 最新稳定版），
    保证多次调用返回相同指纹。

    Returns:
        默认 BrowserFingerprint 实例
    """
    return BrowserFingerprint(_CHROME_VERSIONS[0])


def get_random_fingerprint() -> BrowserFingerprint:
    """获取随机浏览器指纹

    随机选择浏览器版本和操作系统，提高反爬规避能力。

    Returns:
        随机 BrowserFingerprint 实例
    """
    return BrowserFingerprint()


def get_api_headers(
    email: str | None = None,
    api_key: str | None = None,
    bearer_token: str | None = None,
) -> dict[str, str]:
    """获取 API 请求头（非爬虫场景，使用规范的 UA）

    API 场景不需要伪装浏览器，使用标准 SouWen 项目 UA + 可选认证头。

    Args:
        email: 礼貌性 From 邮箱（如 OpenAlex 建议添加）
        api_key: API 密钥，将被放入 X-API-Key 头
        bearer_token: Bearer 令牌，将被放入 Authorization 头

    Returns:
        API 请求头字典

    说明：
        多个认证参数可同时指定，都会被添加到返回头中。
    """
    headers: dict[str, str] = {
        "User-Agent": f"SouWen/{__version__} (Academic & Patent Search; https://github.com/BlueSkyXN/SouWen)",
    }
    if email:
        headers["From"] = email
    if api_key:
        headers["X-API-Key"] = api_key
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    return headers
