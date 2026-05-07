"""GET /sources — 正式 Source Catalog 响应。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from souwen.server.auth import check_user_auth
from souwen.server.schemas import SourceCatalogResponse

router = APIRouter()


@router.get(
    "/sources",
    response_model=SourceCatalogResponse,
    dependencies=[Depends(check_user_auth)],
)
async def list_sources() -> SourceCatalogResponse:
    """列出公开 Source Catalog，并标注当前配置下的可用状态。"""
    from souwen.config import get_config
    from souwen.registry.catalog import public_source_catalog_payload

    return SourceCatalogResponse(**public_source_catalog_payload(get_config()))
