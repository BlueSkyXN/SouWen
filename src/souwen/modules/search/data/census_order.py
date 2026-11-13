"""Search candidate order generated from the P1 direct census.

Source: Actions run 43127424016, warp-off sources report. PASS before WARN,
then mean latency of valid probes that finished within 10 seconds. Sources
that failed every query stay off this list until a later census passes them.

P2 domain consolidation (SPEC 2.2): research_output merged into paper
(datacite/figshare inserted by the same latency rule), developer renamed to
code, cn_tech + social merged into community, knowledge renamed to wiki.
"""

CENSUS_CANDIDATE_ORDER: dict[str, tuple[str, ...]] = {
    "web": ("yahoo",),
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
        "semantic_scholar",
    ),
    "patent": (),
    "book": ("library_of_congress", "open_library", "internet_archive"),
    "code": ("stackoverflow", "github"),
    "community": ("juejin", "coolapk"),
    "wiki": ("wikipedia",),
    "images": (),
    "videos": (),
}
