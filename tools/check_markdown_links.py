"""Validate tracked Markdown local links and heading anchors without network access."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import unicodedata
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt


REPO_ROOT = Path(__file__).resolve().parents[1]
IGNORED_SCHEMES = {"data", "ftp", "http", "https", "mailto", "tel"}


@dataclass(frozen=True, slots=True)
class LinkIssue:
    source: str
    line: int
    target: str
    reason: str


class _HtmlReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[str] = []
        self.anchors: set[str] = set()

    def handle_starttag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for key, value in attrs:
            if value is None:
                continue
            if key in {"href", "src"}:
                self.references.append(value)
            elif key in {"id", "name"}:
                self.anchors.add(value)


def _markdown() -> MarkdownIt:
    return MarkdownIt("commonmark", {"html": True})


def _github_slug(text: str) -> str:
    """Approximate GitHub's Unicode heading slug for repository-local validation."""

    normalized = unescape(text).strip().lower()
    output: list[str] = []
    for char in normalized:
        category = unicodedata.category(char)
        if char.isspace():
            output.append("-")
        elif char in {"-", "_"} or category[0] in {"L", "M", "N"}:
            output.append(char)
    return "".join(output)


def _anchors(text: str) -> set[str]:
    anchors: set[str] = set()
    slug_counts: dict[str, int] = {}
    tokens = _markdown().parse(text)
    for index, token in enumerate(tokens):
        if token.type == "heading_open" and index + 1 < len(tokens):
            inline = tokens[index + 1]
            if inline.type != "inline":
                continue
            base = _github_slug(inline.content)
            if not base:
                continue
            duplicate_index = slug_counts.get(base, 0)
            slug_counts[base] = duplicate_index + 1
            anchors.add(base if duplicate_index == 0 else f"{base}-{duplicate_index}")
        if token.type in {"html_block", "html_inline"}:
            parser = _HtmlReferenceParser()
            parser.feed(token.content)
            anchors.update(parser.anchors)
    return anchors


def _references(text: str) -> list[tuple[int, str]]:
    references: list[tuple[int, str]] = []
    for token in _markdown().parse(text):
        line = (token.map[0] + 1) if token.map else 1
        if token.type == "inline":
            for child in token.children or ():
                if child.type == "link_open":
                    href = child.attrGet("href")
                    if href:
                        references.append((line, href))
                elif child.type == "image":
                    src = child.attrGet("src")
                    if src:
                        references.append((line, src))
        elif token.type in {"html_block", "html_inline"}:
            parser = _HtmlReferenceParser()
            parser.feed(token.content)
            references.extend((line, reference) for reference in parser.references)
    return references


def _tracked_markdown_files(repo_root: Path) -> list[Path]:
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
            "--",
            "*.md",
        ],
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
    )
    return sorted(repo_root / item.decode("utf-8") for item in result.stdout.split(b"\0") if item)


def _has_exact_case(path: Path, repo_root: Path) -> bool:
    try:
        relative = path.relative_to(repo_root)
    except ValueError:
        return False
    current = repo_root
    for part in relative.parts:
        try:
            names = {entry.name for entry in current.iterdir()}
        except OSError:
            return False
        if part not in names:
            return False
        current /= part
    return True


def check_markdown_links(
    repo_root: Path,
    markdown_files: list[Path] | None = None,
) -> tuple[list[LinkIssue], int]:
    files = markdown_files if markdown_files is not None else _tracked_markdown_files(repo_root)
    issues: list[LinkIssue] = []
    link_count = 0
    anchor_cache: dict[Path, set[str]] = {}

    for source in files:
        text = source.read_text(encoding="utf-8")
        for line, target in _references(text):
            parsed = urlsplit(target)
            if parsed.scheme.lower() in IGNORED_SCHEMES or parsed.netloc or target.startswith("//"):
                continue
            if parsed.scheme:
                continue
            if parsed.path.startswith("/"):
                # Web application routes are not repository file paths.
                continue
            link_count += 1
            decoded_path = unquote(parsed.path)
            decoded_fragment = unquote(parsed.fragment)
            destination = source if not decoded_path else source.parent / decoded_path
            try:
                destination = destination.resolve(strict=False)
                destination.relative_to(repo_root.resolve())
            except (OSError, ValueError):
                issues.append(
                    LinkIssue(
                        source=str(source.relative_to(repo_root)),
                        line=line,
                        target=target,
                        reason="target escapes repository root",
                    )
                )
                continue

            if not destination.exists() or not _has_exact_case(destination, repo_root.resolve()):
                issues.append(
                    LinkIssue(
                        source=str(source.relative_to(repo_root)),
                        line=line,
                        target=target,
                        reason="local path does not exist with exact case",
                    )
                )
                continue

            if decoded_fragment and destination.is_file() and destination.suffix.lower() == ".md":
                anchors = anchor_cache.get(destination)
                if anchors is None:
                    anchors = _anchors(destination.read_text(encoding="utf-8"))
                    anchor_cache[destination] = anchors
                if decoded_fragment not in anchors:
                    issues.append(
                        LinkIssue(
                            source=str(source.relative_to(repo_root)),
                            line=line,
                            target=target,
                            reason=f"Markdown anchor not found: #{decoded_fragment}",
                        )
                    )

    return issues, link_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-report", type=Path, help="Write machine-readable evidence")
    args = parser.parse_args()

    files = _tracked_markdown_files(REPO_ROOT)
    issues, link_count = check_markdown_links(REPO_ROOT, files)
    payload = {
        "schema_version": 1,
        "script": "check_markdown_links",
        "overall": "FAIL" if issues else "PASS",
        "file_count": len(files),
        "link_count": link_count,
        "issues": [asdict(issue) for issue in issues],
    }
    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        args.json_report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    for issue in issues:
        print(f"{issue.source}:{issue.line}: {issue.target}: {issue.reason}")
    print(
        f"Markdown links: {payload['overall']} "
        f"({payload['file_count']} files, {link_count} local links, {len(issues)} issues)"
    )
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
