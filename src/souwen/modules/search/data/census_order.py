"""Search candidate order from the latest authoritative census.

Round 3 (run 43469882784, both legs direct): PASS before WARN, then mean
latency of valid probes. Sources failing every query stay off this list.

P3 终判（run 43469882784）后：20 个待浏览器/修一轮源已删除；
brave（本轮 PASS）与 baidu（本轮 PASS）重新入列。
"""

CENSUS_CANDIDATE_ORDER: dict[str, tuple[str, ...]] = {
    "web": ("yahoo", "baidu", "brave"),
    "news": ("duckduckgo_news",),
    "paper": (
        "huggingface",
        "crossref",
        "openalex",
        "datacite",
        "zenodo",
        "eric",
        "pubmed",
        "figshare",
        "europepmc",
        "hal",
        "doaj",
        "iacr",
        "arxiv",
        "openaire",
        "osti",
    ),
    "patent": (),
    "book": ("library_of_congress", "open_library", "internet_archive"),
    "code": ("stackoverflow", "github"),
    "community": ("juejin", "coolapk"),
    "wiki": ("wikipedia",),
    "images": (),
    "videos": (),
}
