# Source census

> 由 `tools/gen_sources_doc.py` 从最近的 census 报告生成；不要手改本文件。
> 判定口径：PASS = 3 查询 ≥2 有效；WARN = 1；FAIL = 0。取两次 leg 中较好的一次。

汇总：FAIL 21 · PASS 26 · WARN 5，共 52 源。

| 源 | 结果 | 有效/总数 | 备注 |
|---|---|---|---|
| `arxiv` | PASS | 3/3 | [warp-off] all probes valid |
| `arxiv_fulltext` | PASS | 3/3 | [warp-off] all probes valid |
| `baidu` | PASS | 2/3 | [warp-on-unavailable-fallback-direct] only 0 valid items |
| `brave` | PASS | 2/3 | [warp-off] gateway_timeout |
| `builtin-fetch` | PASS | 3/3 | [warp-off] all probes valid |
| `crossref` | PASS | 3/3 | [warp-off] all probes valid |
| `datacite` | PASS | 3/3 | [warp-off] all probes valid |
| `doaj` | PASS | 3/3 | [warp-off] all probes valid |
| `eric` | PASS | 3/3 | [warp-off] all probes valid |
| `europepmc` | PASS | 3/3 | [warp-off] all probes valid |
| `figshare` | PASS | 3/3 | [warp-off] all probes valid |
| `github` | PASS | 2/3 | [warp-off] bad_gateway |
| `hal` | PASS | 3/3 | [warp-off] all probes valid |
| `huggingface` | PASS | 3/3 | [warp-off] all probes valid |
| `iacr` | PASS | 2/3 | [warp-off] only 1 valid items |
| `internet_archive` | PASS | 3/3 | [warp-off] all probes valid |
| `jina_reader` | PASS | 3/3 | [warp-off] all probes valid |
| `juejin` | PASS | 3/3 | [warp-off] all probes valid |
| `library_of_congress` | PASS | 3/3 | [warp-off] all probes valid |
| `open_library` | PASS | 2/3 | [warp-off] bad_gateway |
| `openaire` | PASS | 3/3 | [warp-off] all probes valid |
| `openalex` | PASS | 3/3 | [warp-off] all probes valid |
| `pubmed` | PASS | 3/3 | [warp-off] all probes valid |
| `stackoverflow` | PASS | 3/3 | [warp-off] all probes valid |
| `wikipedia` | PASS | 3/3 | [warp-off] all probes valid |
| `yahoo` | PASS | 3/3 | [warp-off] all probes valid |
| `coolapk` | WARN | 1/3 | [warp-off] only 0 valid items |
| `duckduckgo_news` | WARN | 1/3 | [warp-off] gateway_timeout; only 0 valid items |
| `osti` | WARN | 1/3 | [warp-off] bad_gateway |
| `wayback` | WARN | 1/3 | [warp-on-unavailable-fallback-direct] bad_gateway |
| `zenodo` | WARN | 1/3 | [warp-off] bad_gateway |
| `bing` | FAIL | 0/3 | [warp-off] only 0 valid items |
| `bing_cn` | FAIL | 0/3 | [warp-off] only 0 valid items |
| `biorxiv` | FAIL | 0/3 | [warp-off] gateway_timeout |
| `csdn` | FAIL | 0/3 | [warp-off] gateway_timeout; only 0 valid items |
| `doab` | FAIL | 0/3 | [warp-off] only 0 valid items |
| `duckduckgo` | FAIL | 0/3 | [warp-off] only 0 valid items |
| `duckduckgo_images` | FAIL | 0/3 | [warp-off] only 0 valid items |
| `duckduckgo_videos` | FAIL | 0/3 | [warp-off] only 0 valid items |
| `google` | FAIL | 0/3 | [warp-off] only 0 valid items |
| `google_patents` | FAIL | 0/3 | [warp-off] gateway_timeout |
| `hostloc` | FAIL | 0/3 | [warp-off] only 0 valid items |
| `mojeek` | FAIL | 0/3 | [warp-off] gateway_timeout |
| `nodeseek` | FAIL | 0/3 | [warp-off] only 0 valid items |
| `pmc` | FAIL | 0/3 | [warp-off] bad_gateway |
| `searxng` | FAIL | 0/3 | [warp-off] bad_gateway |
| `semantic_scholar` | FAIL | 0/3 | [warp-off] rate_limited |
| `startpage` | FAIL | 0/3 | [warp-off] only 0 valid items |
| `v2ex` | FAIL | 0/3 | [warp-off] only 0 valid items |
| `wikisource` | FAIL | 0/3 | [warp-off] bad_gateway |
| `xiaohongshu` | FAIL | 0/3 | [warp-off] only 0 valid items |
| `yandex` | FAIL | 0/3 | [warp-off] only 0 valid items |
