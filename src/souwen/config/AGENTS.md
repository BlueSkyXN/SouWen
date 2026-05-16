# src/souwen/config navigation card

Type: Domain card.
This directory owns runtime configuration models, templates, loaders and validators.
Read `models.py`, `loader.py`, `validators.py`, `template.py`, `.env.example`, `docs/configuration.md`, and tests covering config before editing.
Read this card for config fields, auth config, environment parsing, YAML/.env merge behavior or source credential changes.

## Local invariants

- Config priority is env > `./souwen.yaml` > `~/.config/souwen/config.yaml` > `.env` > defaults.
- Source credentials must line up with registry `config_field` and `credential_fields`.
- Retired auth fields must continue to fail clearly instead of being accepted silently.
- Loader tests must remain independent of the user's real HOME and local config files.

## Do not

- Do not re-enable `api_password` or `visitor_password`.
- Do not make admin endpoints open unless `SOUWEN_ADMIN_OPEN=1` is explicit.
- Do not hard-code private credentials, cookies or service URLs into defaults/templates.

## Validation

- `pytest tests/test_config.py tests/test_config_loader.py -v --tb=short`
- Source credential impact: `pytest tests/registry/test_consistency.py -v --tb=short`
