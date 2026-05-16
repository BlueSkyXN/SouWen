# cloud navigation card

This directory contains Hugging Face Space and ModelScope deployment wrappers.
Read `docs/hf-space-cd.md`, `docs/deployment.md`, platform README, Dockerfile and entrypoint first.
Read this card for cloud Dockerfiles, entrypoints, platform docs or deployment assumptions.

## Local invariants

- Platform wrappers should track root Dockerfile behavior for panel build, WARP, auth env vars and optional web2pdf.
- Hugging Face uses `app_port: 49265`; ModelScope expects container port `7860`.
- `SOUWEN_ADMIN_OPEN` is only a local/CI debug escape hatch.

## Do not

- Do not hard-code real secrets in images or README files.
- Do not default-enable privileged WARP kernel mode.

## Validation

- `pytest tests/test_dockerfiles.py tests/test_web2pdf_packaging.py -v --tb=short`
- Docker builds may need network and Docker daemon.
