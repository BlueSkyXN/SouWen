# Source census

> 由 `tools/gen_sources_doc.py` 从最近的 census 报告生成；不要手改本文件。
> 判定口径：PASS = 3 查询 ≥2 有效；WARN = 1；FAIL = 0。取两次 leg 中较好的一次。

汇总：FAIL 2 · PASS 26 · WARN 4，共 32 源。

| 源 | 结果 | 有效/总数 | 备注 |
|---|---|---|---|
| `arxiv` | PASS | 3/3 | [best-of-warp-on-off] all probes valid |
| `arxiv_fulltext` | PASS | 3/3 | [best-of-warp-on-off] all probes valid |
| `builtin-fetch` | PASS | 3/3 | [best-of-warp-on-off] all probes valid |
| `crossref` | PASS | 3/3 | [best-of-warp-on-off] all probes valid |
| `datacite` | PASS | 3/3 | [best-of-warp-on-off] all probes valid |
| `doaj` | PASS | 3/3 | [best-of-warp-on-off] all probes valid |
| `duckduckgo_news` | PASS | 2/3 | [best-of-warp-on-off] only 0 valid items |
| `eric` | PASS | 3/3 | [best-of-warp-on-off] all probes valid |
| `europepmc` | PASS | 3/3 | [best-of-warp-on-off] all probes valid |
| `figshare` | PASS | 3/3 | [best-of-warp-on-off] all probes valid |
| `github` | PASS | 2/3 | [best-of-warp-on-off] bad_gateway |
| `hal` | PASS | 3/3 | [best-of-warp-on-off] all probes valid |
| `huggingface` | PASS | 3/3 | [best-of-warp-on-off] all probes valid |
| `iacr` | PASS | 2/3 | [best-of-warp-on-off] only 1 valid items |
| `internet_archive` | PASS | 2/3 | [best-of-warp-on-off] bad_gateway |
| `jina_reader` | PASS | 3/3 | [best-of-warp-on-off] all probes valid |
| `juejin` | PASS | 3/3 | [best-of-warp-on-off] all probes valid |
| `library_of_congress` | PASS | 3/3 | [best-of-warp-on-off] all probes valid |
| `open_library` | PASS | 2/3 | [best-of-warp-on-off] bad_gateway |
| `openaire` | PASS | 3/3 | [best-of-warp-on-off] all probes valid |
| `openalex` | PASS | 3/3 | [best-of-warp-on-off] all probes valid |
| `pubmed` | PASS | 3/3 | [best-of-warp-on-off] all probes valid |
| `stackoverflow` | PASS | 3/3 | [best-of-warp-on-off] all probes valid |
| `wayback` | PASS | 2/3 | [best-of-warp-on-off] bad_gateway |
| `wikipedia` | PASS | 3/3 | [best-of-warp-on-off] all probes valid |
| `zenodo` | PASS | 3/3 | [best-of-warp-on-off] all probes valid |
| `baidu` | WARN | 1/3 | [best-of-warp-on-off] gateway_timeout |
| `coolapk` | WARN | 1/3 | [best-of-warp-on-off] only 0 valid items |
| `osti` | WARN | 1/3 | [best-of-warp-on-off] bad_gateway |
| `yahoo` | WARN | 1/3 | [best-of-warp-on-off] gateway_timeout |
| `brave` | FAIL | 0/3 | [best-of-warp-on-off] gateway_timeout |
| `searxng` | FAIL | 0/3 | [best-of-warp-on-off] bad_gateway |
