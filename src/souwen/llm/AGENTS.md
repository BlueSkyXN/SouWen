# src/souwen/llm navigation card

Type: Domain card.
This directory owns LLM summary/fetch-summary APIs, provider adapters, prompts and response models.
Read `client.py`, `summarize.py`, `fetch_summarize.py`, `prompts.py`, `models.py`, `providers/`, and matching `tests/test_llm/` files first.
Read this card for prompt changes, summary response shape, provider protocol behavior, usage metadata or LLM config integration.

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
