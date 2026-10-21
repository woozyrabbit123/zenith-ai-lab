# IMPACT-0: source-backed Python change-impact candidates

Ask which functions and candidate tests need review after changing a Python
function. The tool follows direct calls through import aliases and module-qualified
names, then walks callers backwards. It never imports or executes project code.

Example: `engine.validate` is called as `check(x)` by `pipeline.run`, which is called
as `launch(1)` by `test_flow.test_good`. Actual `rg -n validate .` misses the test
caller. [The 1,091-byte report](evidence/demo/derived/report.json) shows both paths
with exact source hashes, line numbers and UTF-8 byte spans. These are **syntactic
candidates**, not proof of runtime reachability, regression, or test coverage.

## Run without installing

Linux, Python 3.12+ stdlib. No packages, models, API, Git service, database or daemon
needed by the trace/verify commands. From a reviewed checkout of this stacked PR:

```sh
python experiments/sentinel-impact-0/impact.py trace \
  --root /approved/python-source --symbol engine.validate \
  --out /new/derived-impact --hops 4
```

The root is an explicit approved source directory, not an implicit whole-machine
scan. Module IDs come from relative `.py` paths: `pkg/core.py` → `pkg.core`;
`pkg/__init__.py` → `pkg`; a root `__init__.py` uses the artificial `__root__` ID.
Choose the directory that defines your intended import root. The tool does not
modify sys.path to test importability. Paths must not contain symlinks or `..`;
output must be new and separate. An existing output returns `OUTPUT_EXISTS` and
is preserved. Failed calls may leave derived files; use a fresh output next time.

The compact stdout/report.json is at most 8 KiB. It includes candidate symbols,
distance, next link toward the selected function, test-name hint and exact callee
expression evidence. `graph.json` retains all selected edges, definitions, unknown
references, gaps, original inventory and source snapshot hashes. `.utf8` files
retain original source bytes; a failed non-UTF-8 source remains a gap.

Keep the emitted graph SHA256 outside the output folder. Recheck later:

```sh
python experiments/sentinel-impact-0/impact.py verify \
  --root /approved/python-source --out /existing/derived-impact \
  --graph-sha256 SAVED_GRAPH_SHA256
```

Verification checks the external graph digest, captured current Python source
bytes, retained copies, finite inventory and each edge's exact byte span. It does
not independently prove the analyser's binding decisions. Source mutation, deletion,
changed snapshot/graph or inventory changes fail. Non-Python file contents are
not read or hashed; their paths/kinds are inventoried. No automatic directory
ignores: select a bounded source scope without a huge `.git`, runtime or venv tree.

Exit **0**: candidates returned and captured bytes/spans mechanically PASS.
Exit **1**: incomplete scope, unknown target or no static callers found.
Exit **2**: integrity/scope/resource failure. A verifier can mechanically PASS an
empty graph while the trace correctly reports UNKNOWN_SYMBOL; inspect status,
analysis and candidates too. Nothing ever says `safe_to_edit`.

## What resolves, and what stays unknown

Top-level functions/async functions and direct function calls inside method bodies
are indexed. This supports both free-function test names and class `test_*` methods
as candidate callers. Method **dispatch targets** are not resolved. The binding
subset handles direct names, absolute/relative imports and import aliases; duplicate
or rebound exports, local/parameter/exception/pattern bindings and wildcard imports
are conservatively unknown. Relative imports beyond the chosen root stay unknown.

Every report is `analysis: STATIC_PARTIAL`, `semantic: REVIEW_REQUIRED`, even when
mechanical integrity PASSes and unknown_count is zero. Dynamic dispatch, reflection,
monkey-patching, re-exports, closures/nested bodies, lambdas, generated code,
inheritance and definition-time calls are not exhaustively modelled. Conditional
calls may never run. AST parsing is not a compilation/scoping/executability check.
No automatic test execution or claim about which tests actually cover a function.
No caller found is not evidence that changing the function is safe.

The pinned LENS reader/inventory/span helpers are imported unchanged from PR #3:
base `73239b3afb6838fc057da1e3904c5b3b4df9536b`, engine SHA256
`a1c7e02ada1224a09327eaeee3b5d7d5c7f9e4b969f645ddc33725c49167d814`.
They preserve fd-relative no-follow source reads and exact UTF-8 spans. The graph
algorithm and its verification are specific to Python impact, not LENS document
extraction. This does not claim access to, modification of, or equivalence with
Sentinel's unexported Kit source.

## Reproduce useful evidence

```sh
python -m unittest discover -s experiments/sentinel-impact-0 -p test_impact.py -v
python experiments/sentinel-impact-0/demo.py --work /tmp/impact-demo-new
```

The demo creates three purpose-made Python files; the analyser parses them without
executing them. Its [brief](evidence/demo/brief.md) identifies the aliased pipeline
caller and transitive candidate test. UTF-8/CRLF bytes are unchanged. Name grep and
the graph are compared on the actual files, not invented console output.

A separate read-only run on **three already-public ONECALL files** at commit
`e723864c0cdad9ea2c86ee505d28bcbe679472aa` answers: which native smoke entrypoints
need review if `operator_recipe.cell` changes? [Observed report](evidence/public-probe.json):
`native_smoke.main` at line 50, then the module entrypoint at line 72. All three
source hashes stayed unchanged. There were **148 unresolved external/dynamic
references**, explicitly retained rather than guessed. No whole-repository,
private-code, runtime-call or test-coverage claim.

To reproduce with a local public-lab checkout containing that commit:

```sh
python experiments/sentinel-impact-0/public_probe.py \
  --repo /path/to/zenith-ai-lab --work /tmp/impact-public-new
```

The probe checks the public origin, exports exactly its three declared files from
the immutable commit, then runs the CLI. It never runs those exported sources.

## Bounds and trust

Ceilings: 128 Python files, 512 inventory entries, depth 8, 1 MiB/file, 16 MiB
input and combined derived output, 10k AST nodes/file, 100k/run, 512 calls/file,
2048/run, 1024 definition symbols, 8 hops, 30 seconds overall. Options may only
lower these. Full graph <=2 MiB; result <=8 KiB, including failure packets.
All capped/ambiguous/unreadable/invalid scopes remain GAP/INCOMPLETE or refusal.

Each parser is a child process with 2 s CPU, 3 s wall, 256 MiB address space and
1 MiB stdout/stderr file ceilings. Strict UTF-8 source, no BOM, best-effort Python
3.12 grammar. This prevents a complex parser input from taking down the parent
process in the tested cases. It is not an OS sandbox or a real-time guarantee
against uninterruptible filesystem I/O. No source payload is eval'd, exec'd or
imported. The ordinary Python environment and pinned helper are trusted; this is
not protection against a same-user process replacing code and expected hashes.

## Research and test record

Official references checked before code:

- [Python 3.12 AST](https://docs.python.org/3.12/library/ast.html): locations use
  UTF-8 byte offsets, end offsets exclude the final position, grammar is versioned,
  and parsing does not perform all scoping checks. This informed byte evidence,
  conservative binding rules and the bounded parser subprocess.
- [modulefinder](https://docs.python.org/3.12/library/modulefinder.html): discovers
  imported modules. It is not documented as a function-level reverse impact tool.
  AST is the parser; rg is still useful search. No new generic index/agent framework.

Original ten tests were committed [RED](evidence/red.txt) at `d6306f2` before code.
Later [binding adversaries](evidence/adversarial-red.txt), [exception/pattern
adversary](evidence/binding-red.txt) and [failure-packet cap](evidence/output-red.txt)
exposed real defects before fixes. [Final GREEN](evidence/green.txt): **15/15, no
skips**. This includes aliases, multi-hop tests, class test bodies, package imports,
cycles, Unicode/CRLF, rebinding/shadowing, parser refusal, mutation/tampering,
symlink/FIFO/traversal, count/byte/node/time/output bounds and a source with hostile
top-level effects that was not executed. Existing cached Python 3.14.8 is checked
separately in [this record](evidence/python314.txt); nothing installed this task.

Changes only `experiments/sentinel-impact-0/**`. Existing PRs/main remain unchanged.
No model/API, service, installation, Kit/Hermes/config edit, worker launch, merge or
deployment. Current laptop proof is pending; cloud tests do not imply adoption.
Rollback: close the unmerged stacked PR; nothing installed. Later adoption/revert
is a separate owner decision. Only derived artifacts would need deleting.
