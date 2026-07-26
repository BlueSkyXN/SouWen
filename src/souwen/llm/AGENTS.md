# src/souwen/llm navigation card

Type: Domain card.
This directory owns LLM protocol clients, provider adapters, enriched-search synthesis and response models.
Read `client.py`, `enriched_synthesis.py`, `models.py`, `providers/`, and matching `tests/test_llm/` files first.
Read this card for provider protocol behavior, enriched-synthesis response shape, usage metadata or LLM config integration.

## Local invariants

- Keep OpenAI Chat, OpenAI Responses and Anthropic Messages protocol differences explicit.
- Preserve summary response fields for generated text, citations and usage metadata.
- Use `LLMConfig` for API keys, model settings and key-pool behavior.
- Provider-specific parameters need an explicit model/config field before they reach generic layers.

## Do not

- Do not call real LLM APIs in unit tests.
- Do not leak provider-specific request/response details into generic public models without tests.
- Do not embed real API keys in prompts, fixtures or examples.

## Validation

- `pytest tests/test_llm -v --tb=short`
