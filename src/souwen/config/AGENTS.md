# src/souwen/config navigation card

This directory owns runtime configuration models, loaders and validators.
Read `models.py`, `loader.py`, `validators.py`, `souwen.example.yaml`, and `docs/configuration.md` first.
Read this card for config fields, auth config, environment parsing or source credential changes.

## Key files

- `models.py`: `SouWenConfig`, `SourceChannelConfig`, `LLMConfig`.
- `loader.py`: `.env`, YAML and environment merge order.

## Local invariants

- Config priority is env > `./souwen.yaml` > `~/.config/souwen/config.yaml` > `.env` > defaults.
- Source credentials must line up with registry `config_field` / `credential_fields`.
- Retired auth fields must continue to fail clearly.

## Do not

- Do not re-enable `api_password` or `visitor_password`.
- Do not make admin endpoints open unless `SOUWEN_ADMIN_OPEN=1` is explicit.

## Validation

- `pytest tests/test_config.py tests/test_config_loader.py -v --tb=short`
- Credential/source changes: `pytest tests/registry/test_consistency.py -v`
