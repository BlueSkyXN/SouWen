# Current Python Dependency Baseline v1

**状态**：Phase 1 current-only migration evidence。
**范围**：仅聚合 src/souwen 下 Python 静态导入的 top-level SouWen unit
dependency graph、跨 unit cycle inventory 与关键 legacy edges。
**不是**：目标 allowed graph、Phase 2 dependency gate、Provider Extension v2
实现证明、YAML target workflow 实现证明，或任何业务决策关闭。

Machine-readable aggregate fixture:
[current_python_dependency_graph_v1.json](../../../tests/contracts/fixtures/current_python_dependency_graph_v1.json)

Deterministic verifier:
[test_current_python_dependency_graph_contract.py](../../../tests/contracts/test_current_python_dependency_graph_contract.py)

## 1. Why this baseline exists

Phase 1 needs an auditable answer to “what current Python dependencies actually
exist?” before target directory and import rules can be implemented. The current
tree contains direct legacy coupling between server, registry, Core-adjacent
modules, source/provider modules, plugin lifecycle, and configuration. A target
graph cannot be safely inferred from a desired directory diagram alone.

This baseline intentionally records current facts without approving them. A
passing test means only that the checked-in aggregate fixture matches the
defined AST extraction rule for the current source tree. It does not mean:

- any edge is allowed in the target modular architecture;
- every runtime import, plugin entry point, reflection path, or optional
  dependency is discovered;
- a cycle is accepted, removed, or has a remediation decision;
- an External API, Provider v2, Manifest Registry, Common Runtime, or YAML
  revision mechanism has been implemented; or
- Q-005, Q-006, Q-008, or Q-009 has been closed.

## 2. Extraction algorithm

The test uses Python standard-library pathlib, ast, hashlib, and json against
the repository source tree. It does not import SouWen runtime modules, load
configuration, scan entry points, access the network, or require optional
provider packages.

| Rule | Definition |
|---|---|
| Source set | Every file matching src/souwen/**/*.py, sorted by repository-relative path. |
| Source unit | A direct child file uses its stem; direct __init__.py maps to root; files under a directory map to their first directory component. Examples: search.py -> search; server/routes/fetch.py -> server; registry/sources/paper.py -> registry. |
| Destination unit | Absolute static imports rooted at souwen map to the first component after souwen; importing souwen itself maps to root. |
| Edge | Ordered source-unit -> destination-unit pair, deduplicated. Same-unit imports are excluded because this is a cross-unit graph. |
| Included imports | AST Import and absolute ImportFrom nodes anywhere in executable source, including local imports within functions. |
| TYPE_CHECKING | Imports inside a direct if TYPE_CHECKING or if typing.TYPE_CHECKING body are ignored. The else branch remains eligible. |
| Relative imports | Ignored deliberately. They are package-local syntax and cannot be mapped consistently without resolving each module/package context; this baseline does not attempt that resolution. |
| Dynamic imports | Ignored deliberately, including importlib-style calls, string-based entry points, reflection, and plugin discovery. AST Import/ImportFrom is the complete extraction surface. |
| Non-SouWen imports | Ignored: standard library, third-party, and unrelated package imports are outside the internal graph. |
| Cycles | Strongly connected components with at least two units, computed over the deduplicated cross-unit edge set using deterministic Tarjan traversal. |

The fixture stores the algorithm version, file/node/edge counts, complete
top-level unit inventory, SHA-256 over a canonically sorted compact JSON edge
array, SCC inventory, and a short list of critical legacy edges. It does not
store a hand-maintained per-file dump. This keeps the fixture reviewable while
still making any source-tree edge drift visible through count/hash/cycle checks.

## 3. Current graph snapshot interpretation

The v1 fixture is an aggregate snapshot, not a baseline of intended direction.
Its critical edges make several current legacy facts explicit:

| Current edge | Meaning in current tree | Non-claim |
|---|---|---|
| server -> core | Server code reaches Core helpers/exceptions/session behavior directly. | Not target server/Core port approval. |
| server -> registry | Server routes/schema/readiness consult current registry/source metadata directly. | Not target Provider Manager interface. |
| server -> web | Server routes directly use web/fetch/search implementations. | Not a future server-to-provider dependency rule. |
| server -> llm | Legacy server routes directly use LLM search/summarize support. | Not a target LLMSearchProvider SPI proof. |
| registry -> web | Current registry availability/catalog logic reaches web/local source support. | Not a permitted target registry-to-provider dependency. |
| web -> paper | Current web code has cross-domain dependency. | Not permission for future Provider-to-Provider calls. |

The SCC inventory is only evidence of current top-level aggregation. It is not a
diagnosis of every file-level cycle, nor an assertion that each listed unit
directly imports every other unit in its SCC. Any target remediation needs the
directory/dependency design and migration owner to choose a safe cut.

## 4. Use and update rule

When an intentional current Python import change occurs:

1. run the contract test to obtain observed count/hash/cycles;
2. review whether the new edge is current behavior, legacy coupling, or target
   code that needs a separate Phase 2 rule;
3. update the aggregate fixture only when current-source behavior intentionally
   changes;
4. preserve the exclusions above; do not widen this test into a target checker;
   and
5. review SPEC-05/SPEC-08 separately when the change affects Provider or
   directory migration boundaries.

A fixture mismatch is evidence to inspect source drift. It is not a reason to
edit production imports, suppress a cycle, or modify a target SPEC merely to
restore a hash.

## 5. Known limits

- Relative imports, TYPE_CHECKING-only dependencies, dynamic imports, entry
  points, plugin manifest metadata, runtime conditional imports, subprocesses,
  generated modules, and non-Python components are intentionally not represented.
- Unit aggregation hides file-level direction, import frequency, call paths,
  lazy versus import-time timing, and public/private ownership.
- Hash/count evidence is sensitive to legitimate current-source changes and
  must be reviewed, not blindly regenerated.
- No performance, startup, security, deployment, release, or real-provider
  behavior is measured.
