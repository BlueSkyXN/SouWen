from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "tests/contracts/fixtures/current_python_dependency_graph_v1.json"


def _is_type_checking_guard(test: ast.expr) -> bool:
    return (
        isinstance(test, ast.Name)
        and test.id == "TYPE_CHECKING"
        or isinstance(test, ast.Attribute)
        and isinstance(test.value, ast.Name)
        and test.value.id == "typing"
        and test.attr == "TYPE_CHECKING"
    )


def _source_unit(source_root: Path, path: Path) -> str:
    parts = path.relative_to(source_root).parts
    if len(parts) == 1:
        return "root" if parts[0] == "__init__.py" else Path(parts[0]).stem
    return parts[0]


def _destination_unit(module: str) -> str | None:
    parts = module.split(".")
    if parts[0] != "souwen":
        return None
    return "root" if len(parts) == 1 else parts[1]


class _SouWenAbsoluteImportVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self._inside_type_checking = False
        self.destination_units: list[str] = []

    def visit_If(self, node: ast.If) -> None:
        previous = self._inside_type_checking
        self._inside_type_checking = previous or _is_type_checking_guard(node.test)
        for child in node.body:
            self.visit(child)
        self._inside_type_checking = previous
        for child in node.orelse:
            self.visit(child)

    def visit_Import(self, node: ast.Import) -> None:
        if self._inside_type_checking:
            return
        for alias in node.names:
            destination = _destination_unit(alias.name)
            if destination is not None:
                self.destination_units.append(destination)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self._inside_type_checking or node.level != 0 or node.module is None:
            return
        destination = _destination_unit(node.module)
        if destination is not None:
            self.destination_units.append(destination)


def _current_graph(source_root: Path) -> tuple[list[Path], set[str], set[tuple[str, str]]]:
    files = sorted(source_root.rglob("*.py"))
    units: set[str] = set()
    edges: set[tuple[str, str]] = set()

    for path in files:
        source = _source_unit(source_root, path)
        units.add(source)
        visitor = _SouWenAbsoluteImportVisitor()
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))

        for destination in visitor.destination_units:
            units.add(destination)
            if source != destination:
                edges.add((source, destination))

    return files, units, edges


def _strongly_connected_components(
    units: set[str],
    edges: set[tuple[str, str]],
) -> list[list[str]]:
    adjacency = {
        unit: sorted(destination for source, destination in edges if source == unit)
        for unit in units
    }
    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []
    next_index = 0

    def visit(unit: str) -> None:
        nonlocal next_index
        index[unit] = next_index
        lowlink[unit] = next_index
        next_index += 1
        stack.append(unit)
        on_stack.add(unit)

        for destination in adjacency[unit]:
            if destination not in index:
                visit(destination)
                lowlink[unit] = min(lowlink[unit], lowlink[destination])
            elif destination in on_stack:
                lowlink[unit] = min(lowlink[unit], index[destination])

        if lowlink[unit] != index[unit]:
            return

        component: list[str] = []
        while True:
            destination = stack.pop()
            on_stack.remove(destination)
            component.append(destination)
            if destination == unit:
                break
        if len(component) > 1:
            components.append(sorted(component))

    for unit in sorted(units):
        if unit not in index:
            visit(unit)

    return sorted(components)


def _edge_hash(edges: set[tuple[str, str]]) -> str:
    canonical_edges = sorted([list(edge) for edge in edges])
    encoded = json.dumps(canonical_edges, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@pytest.fixture(scope="module")
def fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_fixture_is_parseable_current_only_baseline(fixture: dict[str, object]) -> None:
    assert fixture["fixture_version"] == 1
    assert fixture["scope"] == "current_only_migration_baseline"
    assert fixture["target_claims_excluded"] == [
        "allowed_target_dependency_graph",
        "phase_2_target_checker_implemented",
        "provider_extension_v2_implemented",
        "yaml_target_workflow_implemented",
    ]
    assert json.loads(json.dumps(fixture, sort_keys=True)) == fixture


def test_current_python_dependency_snapshot_matches_fixture(fixture: dict[str, object]) -> None:
    source_root = REPO_ROOT / str(fixture["source_root"])
    files, units, edges = _current_graph(source_root)
    snapshot = fixture["snapshot"]
    assert isinstance(snapshot, dict)

    assert len(files) == snapshot["python_file_count"]
    assert len(units) == snapshot["top_level_unit_count"]
    assert sorted(units) == snapshot["top_level_units"]
    assert len(edges) == snapshot["cross_unit_edge_count"]
    assert _edge_hash(edges) == snapshot["cross_unit_edge_sha256"]
    assert _strongly_connected_components(units, edges) == snapshot["strongly_connected_components"]


def test_current_critical_legacy_edges_match_fixture(fixture: dict[str, object]) -> None:
    source_root = REPO_ROOT / str(fixture["source_root"])
    _, _, edges = _current_graph(source_root)
    critical_edges = {tuple(edge) for edge in fixture["critical_legacy_edges"]}
    assert critical_edges <= edges
