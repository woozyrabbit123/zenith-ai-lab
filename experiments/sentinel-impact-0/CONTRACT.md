# IMPACT-0 frozen contract

One on-demand, stdlib CLI: `impact.py trace --root ROOT --symbol module.function
--out NEW_DERIVED [--hops 4]`. New changes only in this experiment. Import the
hash-pinned safe directory/read/span helpers from LENS PR #3, never target code.

Scope is top-level Python functions/async functions and module-level calls under
an explicit source root. Resolve direct names, absolute/relative import aliases
and module-qualified references to known scoped functions. Any duplicate/rebound
name, parameter/local shadow, wildcard import, nested scope, method/dynamic or
external call is UNKNOWN rather than an invented resolved edge. All edges mean
syntactic candidates, never definite runtime calls. Conditionals may be unexecuted.
Reverse reachability is bounded, deterministic, cycle-safe. Candidate test names
are hints, not proof of execution/coverage. No static callers found is not safe-to-edit.

Each edge retains a source SHA256, exact UTF-8 byte [start,end) callee expression
and line number. Parse only strict UTF-8; Python 3.12 grammar. AST parsing happens
in a child process, never eval/import/exec of project code; child has 2 s CPU,
3 s wall, 256 MiB address space, 1 MiB stdout/stderr ceilings. Whole run <=30 s.
Freeze files with pinned fd-relative no-follow reads; source copies and full graph
are retained separately. Same-run and later `verify --root ROOT --out DERIVED
--graph-sha256 HASH` check current source hashes, finite inventory, snapshots and
all edge spans. An external expected graph digest is required for later verify.

Ceilings: 128 Python files, 512 entries, depth 8, 1 MiB/file, 16 MiB input/output,
10k AST nodes/file, 100k nodes/run, 512 calls/file, 2048 calls/run, 1024 function
symbols, 8 hops. Non-Python entries are inventoried but not analysed; no implicit
ignore directory. Caps, unreadables, symlinks, syntax/encoding/parser failures or
ambiguous modules are explicit GAP/INCOMPLETE. Compact result <=8 KiB; full graph
<=2 MiB. Original files never edited. Output fresh/separate; no parent traversal.

Mechanical PASS concerns captured bytes/spans only; analysis always STATIC_PARTIAL
and semantic REVIEW_REQUIRED. Parser/schema failure cannot report safe-to-edit.
No packages, model/API, service, install, graph DB, daemon, shell execution, Kit/
Hermes edits, worker launch or merge. Real cloud proof is not laptop adoption.
