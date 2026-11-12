"""Search candidate order generated from the P1 direct census.

Source: Actions run 43127424016, warp-off sources report. PASS before WARN,
then mean latency of valid probes that finished within 10 seconds. Sources
that failed every query stay off this list until a later census passes them.
"""

CENSUS_CANDIDATE_ORDER: dict[str, tuple[str, ...]] = {
    "paper": (
        "huggingface",
        "crossref",
        "openalex",
        "zenodo",
        "eric",
        "pubmed",
        "europepmc",
        "hal",
        "doaj",
        "iacr",
        "arxiv",
        "openaire",
        "osti",
        "semantic_scholar",
    ),
    "book": ("library_of_congress", "open_library", "internet_archive"),
    "research_output": ("datacite", "figshare"),
    "patent": (),
    "web": ("yahoo",),
    "news": ("duckduckgo_news",),
    "images": (),
    "videos": (),
    "social": (),
    "developer": ("stackoverflow", "github"),
    "cn_tech": ("juejin", "coolapk"),
    "knowledge": ("wikipedia",),
}
