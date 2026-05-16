# examples navigation card

Type: Domain card.
This directory contains runnable examples and the minimal plugin example.
Read the target example, `docs/python-api.md`, `docs/plugin-integration-spec.md` when relevant, and public API tests before editing.
Read this card when changing examples, public API usage samples or example plugin references.

## Local invariants

- Examples should use public APIs and clearly state any needed API key or env var.
- Keep examples small and directly runnable from the repository root when possible.
- Live-network examples must not become required offline tests.

## Do not

- Do not commit real tokens, cookies, accounts or private service URLs.
- Do not use private/internal APIs unless the example is explicitly about internals.
- Do not make examples a required deterministic test path if they need live network.

## Validation

- Use root validation commands for ordinary examples.
- Minimal plugin changes: read `examples/minimal-plugin/AGENTS.md`.
