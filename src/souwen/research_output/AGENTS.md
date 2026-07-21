# research_output navigation card

Type: Domain card.
This package contains clients and normalizers for datasets, software, events,
reports and other research outputs that are not coerced into `PaperResult`.

## Local invariants

- Preserve a source's general and concrete resource type independently.
- Preserve rights, identifiers, funding, related identifiers and declared resource
  URLs without inferring download, reuse or redistribution permission.
- Use `SouWenHttpClient`, typed `ResearchOutputResult` fields and registry lazy
  loaders; do not introduce a parallel source list or dispatcher.
- A declared content URL is metadata only: never follow or download it during
  normal search/detail normalization.

## Validation

- `pytest tests/test_research_output -v --tb=short`
- `pytest tests/registry/test_consistency.py tests/registry/test_catalog.py -v --tb=short`
- Put live source checks in `scripts/*_functional_check.py`, not ordinary pytest.
