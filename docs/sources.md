# Source census

> 由 `tools/gen_sources_doc.py` 从最近的 census 报告生成；不要手改本文件。
> 判定口径：PASS = 3 查询 ≥2 有效；WARN = 1；FAIL = 0。取两次 leg 中较好的一次。
> NOT PROBED = 零 Key 镜像里不可用（需免费 Key 且未配置或自建实例未配），不是失败。
> 来源报告 leg：warp-on, warp-off（逐源取较优者，备注里保留该源实际来自哪条 leg）。
> run：[43632256679](https://github.com/BlueSkyXN/SouWen/actions/runs/43632256679)
> 源码 SHA：`283ec2f72a8e7b935af3ff431fa00f6b5a439b27`
> WARP：`warp=on verified after 1 attempts`

汇总：FAIL 1 · PASS 24 · WARN 7 · NOT PROBED 4，共 36 源（其中 32 源有体检结果）。

| 源 | 结果 | 有效/总数 | 备注 |
|---|---|---|---|
| `arxiv` | PASS | 3/3 | [warp-on] all probes valid |
| `arxiv_fulltext` | PASS | 3/3 | [warp-on] all probes valid |
| `builtin-fetch` | PASS | 3/3 | [warp-on] all probes valid |
| `crossref` | PASS | 3/3 | [warp-on] all probes valid |
| `datacite` | PASS | 3/3 | [warp-on] all probes valid |
| `doaj` | PASS | 3/3 | [warp-on] all probes valid |
| `eric` | PASS | 3/3 | [warp-on] all probes valid |
| `europepmc` | PASS | 2/3 | [warp-on] gateway_timeout |
| `figshare` | PASS | 3/3 | [warp-on] all probes valid |
| `github` | PASS | 2/3 | [warp-on] bad_gateway |
| `hal` | PASS | 3/3 | [warp-on] all probes valid |
| `huggingface` | PASS | 3/3 | [warp-on] all probes valid |
| `iacr` | PASS | 2/3 | [warp-on] only 1 valid items |
| `internet_archive` | PASS | 3/3 | [warp-on] all probes valid |
| `jina_reader` | PASS | 3/3 | [warp-on] all probes valid |
| `juejin` | PASS | 3/3 | [warp-on] all probes valid |
| `library_of_congress` | PASS | 3/3 | [warp-on] all probes valid |
| `open_library` | PASS | 2/3 | [warp-on] bad_gateway |
| `openaire` | PASS | 3/3 | [warp-on] all probes valid |
| `openalex` | PASS | 3/3 | [warp-on] all probes valid |
| `pubmed` | PASS | 3/3 | [warp-on] all probes valid |
| `stackoverflow` | PASS | 3/3 | [warp-on] all probes valid |
| `wikipedia` | PASS | 3/3 | [warp-on] all probes valid |
| `zenodo` | PASS | 3/3 | [warp-on] all probes valid |
| `baidu` | WARN | 1/3 | [warp-on] gateway_timeout |
| `brave` | WARN | 1/3 | [warp-off] gateway_timeout |
| `coolapk` | WARN | 1/3 | [warp-on] only 0 valid items |
| `duckduckgo_news` | WARN | 1/3 | [warp-on] gateway_timeout; only 0 valid items |
| `osti` | WARN | 1/3 | [warp-on] bad_gateway |
| `wayback` | WARN | 1/3 | [warp-on] bad_gateway; gateway_timeout |
| `yahoo` | WARN | 1/3 | [warp-on] gateway_timeout |
| `searxng` | FAIL | 0/3 | [warp-on] bad_gateway |
| `epo_ops` | NOT PROBED | – | needs free key: EPO_CONSUMER_KEY, EPO_CONSUMER_SECRET |
| `patentsview` | NOT PROBED | – | needs free key: PATENTSVIEW_API_KEY |
| `uspto_odp` | NOT PROBED | – | needs free key: USPTO_API_KEY |
| `youtube` | NOT PROBED | – | needs free key: YOUTUBE_API_KEY |
