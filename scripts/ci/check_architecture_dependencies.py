"""Enforce statically decidable Phase 2 architecture dependency rules.

The gate intentionally governs only migrated target paths. Legacy packages are
outside its scope until a later migration phase explicitly brings them in.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXCEPTIONS = Path(__file__).with_name("architecture_dependency_exceptions.json")
RULE_IDS = frozenset({f"DEP-{number:03d}" for number in range(1, 11)})
DYNAMIC_RULE_ID = "DEP-DYNAMIC"
EXCEPTION_FIELDS = frozenset(
    {"rule_id", "importer", "imported", "owner", "rationale", "removal_phase", "expiry_date"}
)
GOVERNED_SOURCE_PATHS = (
    Path("src/souwen/modules"),
    Path("src/souwen/providers"),
    Path("src/souwen/platform"),
    Path("src/souwen/common_runtime"),
    Path("src/souwen/delivery"),
    Path("contracts"),
)


class ArchitectureCheckerError(ValueError):
    """Configuration or parse error that prevents a reliable gate result."""


@dataclass(frozen=True, order=True)
class ImportEdge:
    file: str
    line: int
    importer: str
    imported: str


@dataclass(frozen=True, order=True)
class Violation:
    rule_id: str
    file: str
    line: int
    importer: str
    imported: str

    def format(self) -> str:
        return (
            f"{self.rule_id} {self.file}:{self.line} "
            f"importer={self.importer} imported={self.imported}"
        )


@dataclass(frozen=True)
class ExceptionEntry:
    rule_id: str
    importer: str
    imported: str
    owner: str
    rationale: str
    removal_phase: str
    expiry_date: date

    def matches(self, violation: Violation) -> bool:
        return (
            self.rule_id == violation.rule_id
            and self.importer == violation.importer
            and self.imported == violation.imported
        )


def _is_module(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(f"{prefix}.")


def _module_name(root: Path, path: Path) -> str:
    relative = path.relative_to(root)
    if relative.parts[0] == "src":
        parts = list(relative.parts[1:])
    else:
        parts = list(relative.parts)
    if parts[-1] == "__init__.py":
        parts.pop()
    else:
        parts[-1] = Path(parts[-1]).stem
    return ".".join(parts)


def _resolve_import_from(importer: str, path: Path, node: ast.ImportFrom) -> str:
    module = node.module or ""
    if node.level == 0:
        return module

    package = importer if path.name == "__init__.py" else importer.rpartition(".")[0]
    package_parts = package.split(".") if package else []
    upward = node.level - 1
    if upward >= len(package_parts):
        return module
    anchor = package_parts[: len(package_parts) - upward]
    return ".".join((*anchor, *([module] if module else [])))


def _dynamic_import_reference(
    node: ast.expr,
    importlib_names: set[str],
    builtins_names: set[str],
    direct_names: set[str],
) -> bool:
    if isinstance(node, ast.Name):
        return node.id in direct_names
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and (
            (node.attr == "import_module" and node.value.id in importlib_names)
            or (node.attr == "__import__" and node.value.id in builtins_names)
        )
    )


def _parse_imports(root: Path, path: Path) -> list[ImportEdge]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        raise ArchitectureCheckerError(f"cannot parse {path.relative_to(root)}: {exc}") from exc

    relative_file = path.relative_to(root).as_posix()
    importer = _module_name(root, path)
    edges: list[ImportEdge] = []
    importlib_names: set[str] = set()
    builtins_names: set[str] = set()
    direct_import_names: set[str] = {"__import__"}
    import_alias_assignments: list[tuple[str, ast.expr]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                edges.append(ImportEdge(relative_file, node.lineno, importer, alias.name))
                if alias.name == "importlib" or alias.name.startswith("importlib."):
                    importlib_names.add(alias.asname or alias.name.split(".", maxsplit=1)[0])
                if alias.name == "builtins":
                    builtins_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            imported = _resolve_import_from(importer, path, node)
            if imported:
                gateway_aliases = imported in {"souwen", "souwen.server", "souwen.deploy"}
                named_aliases = [alias for alias in node.names if alias.name != "*"]
                if not gateway_aliases or not named_aliases:
                    edges.append(ImportEdge(relative_file, node.lineno, importer, imported))
                if gateway_aliases:
                    edges.extend(
                        ImportEdge(
                            relative_file,
                            node.lineno,
                            importer,
                            f"{imported}.{alias.name}",
                        )
                        for alias in named_aliases
                    )
            if node.level == 0 and node.module == "importlib":
                for alias in node.names:
                    if alias.name == "import_module":
                        direct_import_names.add(alias.asname or alias.name)
            if node.level == 0 and node.module == "builtins":
                for alias in node.names:
                    if alias.name == "__import__":
                        direct_import_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Assign):
            import_alias_assignments.extend(
                (target.id, node.value) for target in node.targets if isinstance(target, ast.Name)
            )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
            import_alias_assignments.append((node.target.id, node.value))

    unresolved_aliases = import_alias_assignments
    while unresolved_aliases:
        remaining: list[tuple[str, ast.expr]] = []
        discovered = False
        for target, value in unresolved_aliases:
            if _dynamic_import_reference(
                value, importlib_names, builtins_names, direct_import_names
            ):
                direct_import_names.add(target)
                discovered = True
            else:
                remaining.append((target, value))
        if not discovered:
            break
        unresolved_aliases = remaining

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _dynamic_import_reference(
            node.func, importlib_names, builtins_names, direct_import_names
        ):
            continue
        if (
            node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            edges.append(ImportEdge(relative_file, node.lineno, importer, node.args[0].value))
        else:
            edges.append(ImportEdge(relative_file, node.lineno, importer, "<dynamic>"))
    return edges


def _provider_identity(module: str) -> str:
    parts = module.split(".")
    return ".".join(parts[:4]) if len(parts) >= 4 else ".".join(parts[:3])


def _rule_for(edge: ImportEdge) -> str | None:
    importer = edge.importer
    imported = edge.imported
    if imported == "<dynamic>":
        return DYNAMIC_RULE_ID
    if _is_module(importer, "souwen.modules"):
        if _is_module(imported, "souwen.providers"):
            return "DEP-001"
        if (
            _is_module(imported, "fastapi")
            or _is_module(imported, "panel")
            or _is_module(imported, "web")
            or _is_module(imported, "souwen.web")
            or _is_module(imported, "souwen.server.warp")
            or _is_module(imported, "souwen.server.warp_installer")
            or _is_module(imported, "souwen.deploy.process")
        ):
            return "DEP-005"
    if _is_module(importer, "souwen.providers"):
        if _is_module(imported, "souwen.delivery"):
            return "DEP-002"
        if _is_module(imported, "souwen.providers") and _provider_identity(
            importer
        ) != _provider_identity(imported):
            return "DEP-003"
    if (
        _is_module(importer, "souwen.common_runtime")
        and _is_module(imported, "souwen")
        and not _is_module(imported, "souwen.common_runtime")
    ):
        return "DEP-004"
    if _is_module(importer, "souwen.delivery.api") and _is_module(imported, "souwen.providers"):
        return "DEP-006"
    if _is_module(importer, "contracts") and _is_module(imported, "souwen"):
        return "DEP-009"
    return None


def _iter_governed_files(root: Path) -> Iterable[Path]:
    for relative_path in GOVERNED_SOURCE_PATHS:
        directory = root / relative_path
        if directory.is_dir():
            yield from sorted(directory.rglob("*.py"))


def _top_level_package_violations(root: Path) -> list[Violation]:
    source_root = root / "src"
    if not source_root.is_dir():
        return []
    violations: list[Violation] = []
    for package_path in sorted(path for path in source_root.iterdir() if path.is_dir()):
        package_name = package_path.name
        if package_name == "souwen":
            continue
        python_files = sorted(package_path.rglob("*.py"))
        if not python_files:
            continue
        violations.append(
            Violation(
                "DEP-010",
                python_files[0].relative_to(root).as_posix(),
                1,
                package_name,
                package_path.relative_to(root).as_posix(),
            )
        )
    return violations


def load_exceptions(path: Path, *, today: date | None = None) -> tuple[ExceptionEntry, ...]:
    effective_today = today or date.today()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArchitectureCheckerError(f"cannot load exceptions {path}: {exc}") from exc
    if not isinstance(payload, dict) or set(payload) != {"version", "exceptions"}:
        raise ArchitectureCheckerError("exceptions must contain only version and exceptions")
    if payload["version"] != 1 or not isinstance(payload["exceptions"], list):
        raise ArchitectureCheckerError("exceptions must use version 1 with an exceptions array")

    entries: list[ExceptionEntry] = []
    for index, item in enumerate(payload["exceptions"]):
        if not isinstance(item, dict) or set(item) != EXCEPTION_FIELDS:
            raise ArchitectureCheckerError(
                f"exception {index} must contain exactly {sorted(EXCEPTION_FIELDS)}"
            )
        if any(not isinstance(value, str) or not value.strip() for value in item.values()):
            raise ArchitectureCheckerError(f"exception {index} values must be non-empty strings")
        if "*" in item["importer"] or "*" in item["imported"]:
            raise ArchitectureCheckerError(f"exception {index} cannot use wildcards")
        if item["rule_id"] not in RULE_IDS | {DYNAMIC_RULE_ID}:
            raise ArchitectureCheckerError(
                f"exception {index} has unknown rule_id {item['rule_id']}"
            )
        try:
            expiry_date = date.fromisoformat(item["expiry_date"])
        except ValueError as exc:
            raise ArchitectureCheckerError(f"exception {index} has invalid expiry_date") from exc
        if expiry_date < effective_today:
            raise ArchitectureCheckerError(
                f"exception {index} expired on {expiry_date.isoformat()}"
            )
        entries.append(
            ExceptionEntry(
                item["rule_id"],
                item["importer"],
                item["imported"],
                item["owner"],
                item["rationale"],
                item["removal_phase"],
                expiry_date,
            )
        )
    return tuple(entries)


def check_repository(root: Path, exceptions_path: Path) -> list[Violation]:
    exceptions = load_exceptions(exceptions_path)
    violations = _top_level_package_violations(root)
    for path in _iter_governed_files(root):
        for edge in _parse_imports(root, path):
            rule_id = _rule_for(edge)
            if rule_id is not None:
                violations.append(
                    Violation(rule_id, edge.file, edge.line, edge.importer, edge.imported)
                )
    remaining = [
        violation
        for violation in violations
        if not any(exception.matches(violation) for exception in exceptions)
    ]
    return sorted(set(remaining))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check Phase 2 architecture dependencies.")
    parser.add_argument(
        "--root", type=Path, default=REPOSITORY_ROOT, help="Repository root to inspect."
    )
    parser.add_argument(
        "--exceptions",
        type=Path,
        default=DEFAULT_EXCEPTIONS,
        help="Exact, expiring exception JSON file.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    exceptions_path = args.exceptions.resolve()
    try:
        violations = check_repository(root, exceptions_path)
    except ArchitectureCheckerError as exc:
        print(f"architecture dependency checker configuration error: {exc}", file=sys.stderr)
        return 2
    if violations:
        for violation in violations:
            print(violation.format())
        return 1
    print("architecture dependency check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
