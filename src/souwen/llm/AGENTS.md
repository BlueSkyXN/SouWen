# src/souwen/llm navigation card

This directory owns LLM summary and provider adapters.
Read `client.py`, `prompts.py`, `providers/`, `LLMConfig` in `config/models.py`, and `tests/test_llm/` first.
Read this card for prompt, summary response, provider protocol or LLM config changes.

## Local invariants

- Keep OpenAI Chat, OpenAI Responses and Anthropic Messages protocol differences explicit.
- Preserve summary response fields for generated text, citations and usage metadata.
- Use `LLMConfig` for API key and model settings, including key-pool behavior.

## Do not

- Do not call real LLM APIs in unit tests.
- Do not leak provider-specific parameters into generic layers without a model/config field.

## Validation

- `pytest tests/test_llm -v --tb=short`
