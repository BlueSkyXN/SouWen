"""Read-only, redacted admin configuration view."""

from __future__ import annotations

from fastapi import APIRouter

from souwen.common_runtime.provider_support.redaction import redact_llm_search_gateway_config_view
from souwen.server.routes._common import redact_secret_payload
from souwen.server.schemas import AdminConfigResponse


router = APIRouter()


@router.get("/config", response_model=AdminConfigResponse)
async def get_config_view():
    """Return the current configuration after redacting every credential field."""

    from souwen.config import SouWenConfig, get_config

    cfg = get_config()
    result = {}
    for field_name in SouWenConfig.model_fields:
        value = getattr(cfg, field_name)
        result[field_name] = (
            redact_llm_search_gateway_config_view(value)
            if field_name == "llm_search_gateways"
            else redact_secret_payload(value, field_name)
        )
    return result
