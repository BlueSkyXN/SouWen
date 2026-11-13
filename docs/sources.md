# Source census

> 由 `tools/gen_sources_doc.py` 从最近的 census 报告生成；不要手改本文件。
> 判定口径：PASS = 3 查询 ≥2 有效；WARN = 1；FAIL = 0。取两次 leg 中较好的一次。

汇总：FAIL 4 · PASS 23 · WARN 5，共 32 源。

| 源 | 结果 | 有效/总数 | 备注 |
|---|---|---|---|
| `arxiv` | PASS | 3/3 | [warp-on] all probes valid |
| `arxiv_fulltext` | PASS | 3/3 | [warp-on] all probes valid |
| `builtin-fetch` | PASS | 3/3 | [warp-on] all probes valid |
| `crossref` | PASS | 3/3 | [warp-on] all probes valid |
| `datacite` | PASS | 3/3 | [warp-on] all probes valid |
| `doaj` | PASS | 3/3 | [warp-on] all probes valid |
| `eric` | PASS | 3/3 | [warp-on] all probes valid |
| `europepmc` | PASS | 3/3 | [warp-on] all probes valid |
| `figshare` | PASS | 3/3 | [warp-on] all probes valid |
| `github` | PASS | 2/3 | [warp-on] bad_gateway |
| `hal` | PASS | 3/3 | [warp-on] all probes valid |
| `huggingface` | PASS | 3/3 | [warp-on] all probes valid |
| `iacr` | PASS | 2/3 | [warp-on] only 1 valid items |
| `internet_archive` | PASS | 3/3 | [warp-on] all probes valid |
| `jina_reader` | PASS | 3/3 | [warp-on] all probes valid |
| `juejin` | PASS | 3/3 | [warp-on] all probes valid |
| `open_library` | PASS | 2/3 | [warp-on] bad_gateway |
| `openaire` | PASS | 3/3 | [warp-on] all probes valid |
| `openalex` | PASS | 3/3 | [warp-on] all probes valid |
| `pubmed` | PASS | 3/3 | [warp-on] all probes valid |
| `stackoverflow` | PASS | 3/3 | [warp-on] all probes valid |
| `wikipedia` | PASS | 3/3 | [warp-on] all probes valid |
| `yahoo` | PASS | 3/3 | [warp-on] all probes valid |
| `baidu` | WARN | 1/3 | [warp-on] gateway_timeout; only 0 valid items |
| `coolapk` | WARN | 1/3 | [warp-on] only 0 valid items |
| `duckduckgo_news` | WARN | 1/3 | [warp-on] gateway_timeout; only 0 valid items |
| `osti` | WARN | 1/3 | [warp-on] bad_gateway |
| `zenodo` | WARN | 1/3 | [warp-on] bad_gateway |
| `brave` | FAIL | 0/3 | [warp-on] gateway_timeout |
| `library_of_congress` | FAIL | 0/3 | [warp-on] gateway_timeout |
| `searxng` | FAIL | 0/3 | [warp-on] bad_gateway |
| `wayback` | FAIL | 0/3 | [warp-on] bad_gateway; gateway_timeout |
