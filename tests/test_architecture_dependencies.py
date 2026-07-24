"""Deterministic fixtures for the repository-owned architecture dependency gate."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


CI_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "ci"
if str(CI_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(CI_SCRIPTS))

import check_architecture_dependencies as checker  # noqa: E402


def _write(root: Path, relative_path: str, content: str = "") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _repository(tmp_path: Path) -> tuple[Path, Path]:
    _write(tmp_path, "src/souwen/__init__.py")
    exceptions = _write(
        tmp_path,
        "exceptions.json",
        '{"version": 1, "exceptions": []}\n',
    )
    return tmp_path, exceptions


def _violations(root: Path, exceptions: Path) -> list[checker.Violation]:
    return checker.check_repository(root, exceptions)


def test_allowed_target_edges_pass(tmp_path: Path) -> None:
    root, exceptions = _repository(tmp_path)
    _write(
        root,
        "src/souwen/modules/search/application/service.py",
        "from souwen.common_runtime.transport import Client\n",
    )
    _write(
        root,
        "src/souwen/providers/information_sources/openalex/adapter.py",
        "from souwen.common_runtime.transport import Client\n",
    )
    _write(
        root,
        "src/souwen/common_runtime/transport/client.py",
        "from ..security import policy\n"
        "from souwen import common_runtime\n"
        "import asyncio\n"
        "import httpx\n",
    )

    assert _violations(root, exceptions) == []


@pytest.mark.parametrize(
    "imported",
    [
        "souwen",
        "souwen.core",
        "souwen.delivery",
        "souwen.server",
        "souwen.config",
        "souwen.registry",
        "souwen.platform",
        "souwen.modules.search",
        "souwen.providers.information_sources.openalex",
        "souwen.paper.openalex",
        "souwen.web.builtin",
    ],
)
def test_common_runtime_rejects_every_other_souwen_namespace(tmp_path: Path, imported: str) -> None:
    root, exceptions = _repository(tmp_path)
    relative_path = "src/souwen/common_runtime/transport/client.py"
    _write(root, relative_path, f"import {imported}\n")

    violations = _violations(root, exceptions)

    assert [
        (violation.rule_id, violation.file, violation.line, violation.imported)
        for violation in violations
    ] == [("DEP-004", relative_path, 1, imported)]


@pytest.mark.parametrize(
    ("relative_path", "source", "rule_id"),
    [
        (
            "src/souwen/modules/search/application/service.py",
            "from souwen.providers.information_sources.openalex import adapter\n",
            "DEP-001",
        ),
        (
            "src/souwen/providers/information_sources/openalex/adapter.py",
            "from souwen.delivery.api import routes\n",
            "DEP-002",
        ),
        (
            "src/souwen/providers/information_sources/openalex/adapter.py",
            "from souwen.providers.information_sources.crossref import adapter\n",
            "DEP-003",
        ),
        (
            "src/souwen/common_runtime/transport/client.py",
            "from souwen.modules.search import api\n",
            "DEP-004",
        ),
        (
            "src/souwen/modules/fetch/application/service.py",
            "from fastapi import Depends\n",
            "DEP-005",
        ),
        (
            "src/souwen/delivery/api/routes.py",
            "from souwen.providers.fetch_sources.builtin import client\n",
            "DEP-006",
        ),
        (
            "contracts/golden.py",
            "from souwen.modules.search import api\n",
            "DEP-009",
        ),
    ],
)
def test_statically_decidable_forbidden_edges_fail(
    tmp_path: Path, relative_path: str, source: str, rule_id: str
) -> None:
    root, exceptions = _repository(tmp_path)
    _write(root, relative_path, source)

    violations = _violations(root, exceptions)

    assert [violation.rule_id for violation in violations] == [rule_id]
    assert violations[0].file == relative_path
    assert violations[0].line == 1


def test_relative_and_literal_dynamic_imports_are_resolved(tmp_path: Path) -> None:
    root, exceptions = _repository(tmp_path)
    relative_path = "src/souwen/modules/search/application/service.py"
    _write(
        root,
        relative_path,
        "from ....providers.information_sources.openalex import adapter\n"
        "import importlib as imports\n"
        "imports.import_module('souwen.providers.fetch_sources.builtin.client')\n",
    )

    violations = _violations(root, exceptions)

    assert [
        (violation.rule_id, violation.line, violation.imported) for violation in violations
    ] == [
        ("DEP-001", 1, "souwen.providers.information_sources.openalex"),
        ("DEP-001", 3, "souwen.providers.fetch_sources.builtin.client"),
    ]


@pytest.mark.parametrize(
    ("relative_path", "source", "rule_id", "imported"),
    [
        (
            "src/souwen/modules/search/application/service.py",
            "from souwen import providers\n",
            "DEP-001",
            "souwen.providers",
        ),
        (
            "src/souwen/providers/information_sources/openalex/adapter.py",
            "from souwen import delivery\n",
            "DEP-002",
            "souwen.delivery",
        ),
        (
            "src/souwen/common_runtime/transport/client.py",
            "from souwen import modules\n",
            "DEP-004",
            "souwen.modules",
        ),
        (
            "src/souwen/modules/fetch/application/service.py",
            "from souwen.server import warp\n",
            "DEP-005",
            "souwen.server.warp",
        ),
    ],
)
def test_import_from_gateway_aliases_cannot_bypass_rules(
    tmp_path: Path, relative_path: str, source: str, rule_id: str, imported: str
) -> None:
    root, exceptions = _repository(tmp_path)
    _write(root, relative_path, source)

    violations = _violations(root, exceptions)

    assert [(violation.rule_id, violation.imported) for violation in violations] == [
        (rule_id, imported)
    ]


def test_common_runtime_gateway_aliases_cannot_bypass_dep_004(tmp_path: Path) -> None:
    root, exceptions = _repository(tmp_path)
    relative_path = "src/souwen/common_runtime/transport/client.py"
    _write(root, relative_path, "from souwen import core, config, registry, platform, server\n")

    violations = _violations(root, exceptions)

    assert [
        (violation.rule_id, violation.line, violation.imported) for violation in violations
    ] == [
        ("DEP-004", 1, "souwen.config"),
        ("DEP-004", 1, "souwen.core"),
        ("DEP-004", 1, "souwen.platform"),
        ("DEP-004", 1, "souwen.registry"),
        ("DEP-004", 1, "souwen.server"),
    ]


def test_nonliteral_dynamic_import_fails_with_stable_rule_id(tmp_path: Path) -> None:
    root, exceptions = _repository(tmp_path)
    _write(
        root,
        "src/souwen/modules/search/application/service.py",
        "from importlib import import_module\nname = 'souwen.providers.example'\nimport_module(name)\n",
    )

    violations = _violations(root, exceptions)

    assert [
        (violation.rule_id, violation.line, violation.imported) for violation in violations
    ] == [(checker.DYNAMIC_RULE_ID, 3, "<dynamic>")]


@pytest.mark.parametrize(
    ("source", "rule_id", "line", "imported"),
    [
        ('__import__("souwen.core.http_client")\n', "DEP-004", 1, "souwen.core.http_client"),
        (
            "module_name = 'souwen.core.http_client'\n__import__(module_name)\n",
            "DEP-DYNAMIC",
            2,
            "<dynamic>",
        ),
        (
            'load = __import__\nload("souwen.core.http_client")\n',
            "DEP-004",
            2,
            "souwen.core.http_client",
        ),
        (
            "load = __import__\nname = 'souwen.core.http_client'\nload(name)\n",
            "DEP-DYNAMIC",
            3,
            "<dynamic>",
        ),
        (
            'from builtins import __import__ as load\nload("souwen.core.http_client")\n',
            "DEP-004",
            2,
            "souwen.core.http_client",
        ),
        (
            'import builtins as runtime\nruntime.__import__("souwen.core.http_client")\n',
            "DEP-004",
            2,
            "souwen.core.http_client",
        ),
        (
            'load = __import__\nindirect = load\nindirect("souwen.core.http_client")\n',
            "DEP-004",
            3,
            "souwen.core.http_client",
        ),
    ],
)
def test_builtin_import_cannot_bypass_architecture_rules(
    tmp_path: Path, source: str, rule_id: str, line: int, imported: str
) -> None:
    root, exceptions = _repository(tmp_path)
    relative_path = "src/souwen/common_runtime/transport/client.py"
    _write(root, relative_path, source)

    violations = _violations(root, exceptions)

    assert [
        (violation.rule_id, violation.line, violation.imported) for violation in violations
    ] == [(rule_id, line, imported)]


def test_platform_is_governed_for_dynamic_imports(tmp_path: Path) -> None:
    root, exceptions = _repository(tmp_path)
    _write(
        root,
        "src/souwen/platform/provider_manager/loader.py",
        "from importlib import import_module\nmodule_name = 'provider.factory'\nimport_module(module_name)\n",
    )

    violations = _violations(root, exceptions)

    assert [
        (violation.rule_id, violation.line, violation.imported) for violation in violations
    ] == [(checker.DYNAMIC_RULE_ID, 3, "<dynamic>")]


def test_top_level_package_and_exact_expiring_exception_rules(tmp_path: Path) -> None:
    root, exceptions = _repository(tmp_path)
    _write(root, "src/rogue/__init__.py")

    violations = _violations(root, exceptions)
    assert [
        (violation.rule_id, violation.importer, violation.imported) for violation in violations
    ] == [("DEP-010", "rogue", "src/rogue")]

    exceptions.write_text(
        """{
  "version": 1,
  "exceptions": [
    {
      "rule_id": "DEP-010",
      "importer": "rogue",
      "imported": "src/rogue",
      "owner": "architecture",
      "rationale": "bounded migration fixture",
      "removal_phase": "Phase 2B",
      "expiry_date": "2999-01-01"
    }
  ]
}
""",
        encoding="utf-8",
    )
    assert _violations(root, exceptions) == []


def test_namespace_package_outside_souwen_fails_dep_010(tmp_path: Path) -> None:
    root, exceptions = _repository(tmp_path)
    _write(root, "src/rogue_namespace/module.py")

    violations = _violations(root, exceptions)

    assert [
        (violation.rule_id, violation.file, violation.importer, violation.imported)
        for violation in violations
    ] == [("DEP-010", "src/rogue_namespace/module.py", "rogue_namespace", "src/rogue_namespace")]


@pytest.mark.parametrize(
    "payload",
    [
        '{"version": 1, "exceptions": [{"rule_id": "DEP-001"}]}',
        """{
  "version": 1,
  "exceptions": [{
    "rule_id": "DEP-001", "importer": "souwen.modules.*",
    "imported": "souwen.providers.source", "owner": "architecture",
    "rationale": "bad", "removal_phase": "Phase 2B", "expiry_date": "2999-01-01"
  }]
}""",
        """{
  "version": 1,
  "exceptions": [{
    "rule_id": "DEP-001", "importer": "souwen.modules.search",
    "imported": "souwen.providers.source", "owner": "architecture",
    "rationale": "expired", "removal_phase": "Phase 2B", "expiry_date": "2000-01-01"
  }]
}""",
    ],
)
def test_exception_schema_rejects_incomplete_wildcard_and_expired_entries(
    tmp_path: Path, payload: str
) -> None:
    root, exceptions = _repository(tmp_path)
    exceptions.write_text(payload, encoding="utf-8")

    with pytest.raises(checker.ArchitectureCheckerError):
        checker.load_exceptions(exceptions)


def test_cli_returns_one_with_stable_evidence_and_zero_when_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, exceptions = _repository(tmp_path)
    relative_path = "src/souwen/modules/search/application/service.py"
    _write(
        root, relative_path, "from souwen.providers.information_sources.openalex import adapter\n"
    )

    assert checker.main(["--root", str(root), "--exceptions", str(exceptions)]) == 1
    assert capsys.readouterr().out == (
        "DEP-001 src/souwen/modules/search/application/service.py:1 "
        "importer=souwen.modules.search.application.service "
        "imported=souwen.providers.information_sources.openalex\n"
    )

    _write(root, relative_path, "from souwen.common_runtime.transport import Client\n")
    assert checker.main(["--root", str(root), "--exceptions", str(exceptions)]) == 0
    assert capsys.readouterr().out == "architecture dependency check passed\n"


def test_cli_returns_two_for_invalid_exception_configuration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, exceptions = _repository(tmp_path)
    exceptions.write_text("{}\n", encoding="utf-8")

    assert checker.main(["--root", str(root), "--exceptions", str(exceptions)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("architecture dependency checker configuration error:")
