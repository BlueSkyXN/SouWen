"""core/scraper/ — 爬虫平台层。

BaseScraper 在 `base.py` 中；子类（如 GooglePatentsScraper）位于业务 domain 下。
"""

from souwen.core.scraper.base import BaseScraper  # noqa: F401

__all__ = ["BaseScraper"]
