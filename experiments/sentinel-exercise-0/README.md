# Sentinel EXERCISE-0

Prove which trusted unittest contexts actually enter one selected Python function.
A green suite alone cannot tell you this. Aliases and dynamic method dispatch are
observed when they enter the selected code; a passing decoy is reported separately.
This complements IMPACT-0's static candidates. It does not select a safe subset of
all tests or prove that assertions are effective.

## Run once

Requires Linux/POSIX, Python 3.12+ and the unchanged sibling LENS-0 helper (PR #3).
No packages, service, model API or installation. Review and approve the entire
project/test scope before executing it:

```sh
python experiments/sentinel-exercise-0/exercise.py run \
  --root /approved/bounded/source-and-tests \
  --target engine.py:validate --out /approved/new-derived
```

Target syntax is a relative `.py` file and exact `co_qualname`, such as
`engine.py:Service.validate`. Output must be new, separate from input, and have an
existing parent. Every regular input file is snapshotted, including data/cache
files; there are no implicit ignores. Choose a small, explicitly approved root.

Discovery uses unittest's `test_*.py` pattern by default. Narrow it with `--pattern`;
`--tests 64 --wall 10 --cpu 5 --log-bytes 262144` are the defaults. Test bodies run
only after discovery and test-count/identity validation. Discovery itself executes
imports and load_tests hooks, so the test cap is not an import-execution cap.

The compact JSON packet is also saved as `packet.json`; `result.json` retains all
test IDs, PASS/FAIL/ERROR/SKIP/XFAIL/XPASS (including parent subtest failures) and
call-event counts. Skipped subtests may have separate result rows. Class fixture
errors/skips that prevent execution produce incomplete execution, with diagnostic
rows retained. `stdout.log`, `stderr.log`, worker response/diagnostic files, the
manifest and raw `.source` snapshots stay local. They may contain approved input
and test output; choose their storage accordingly. Failure tracebacks are not
serialized into test rows; this tool is an attribution summary, not a test runner
UI replacement.

| Packet status | Meaning | Exit |
| --- | --- | --- |
| OBSERVED | At least one context entered selected code; suite successful; checks complete | 0 |
| OBSERVED_WITH_FAILURE | Entry observed; unittest reported failure/error/XPASS | 1 |
| NOT_OBSERVED_IN_SCOPE | No credited entry; inspect test_result independently | 1 |
| INCOMPLETE / ERROR | Scope, target, integrity, instrumentation or resource gap | 2 |

XFAIL and SKIP follow native unittest suite-success semantics. Neither is evidence
of a passing assertion. A no-entry result can accompany a failing suite. Incomplete
results can retain observations, but cannot yield clean observation proof. Missing
or duplicate qualified targets refuse discovery; duplicate test IDs refuse bodies.

## What is actually measured

The child compiles source without executing it to identify exactly one target code
object. Events must match source-relative file, qualified name, first line and a
SHA256 signature of bytecode, constants, names, arguments and exception table. This
signature is interpreter-specific, not portable across Python versions. The source
SHA256 independently binds original bytes. A same-name function elsewhere, changed
constant, or replacement lambda does not receive original-function credit.

`sys.setprofile` reports **main-thread Python call events**. A unittest result's
startTest/stopTest brackets the context. setUp/tearDown/cleanup calls count for that
test; discovery and class hooks are unassigned. Generator resumes can each produce
a call event (two yields plus completion => three events). Counts are not function
invocations. Other threads/processes, C code, line/branch coverage and assertion
quality are outside scope. Absence means NOT_OBSERVED_IN_SCOPE, never dead code,
uncovered, safe-to-edit, or a complete coverage statement.

Before and after execution, the parent compares all scoped source/data bytes,
snapshot bytes, the manifest and inventory. These checks establish checkpoint byte
integrity, not absence of transient writes. Persistent profiler replacement/loss,
code mismatch, source mutation, missing results and limits invalidate clean proof.
Temporarily disabling and restoring profiling can hide calls. Tests can also tamper
with Python process internals. **Only run trusted code.**

## Bounds and trust

This executes caller-approved code with the caller's inherited filesystem/network
access and environment. It is **not an OS sandbox** or a mechanism for running
untrusted repositories. No credential isolation or malicious-test resistance is
claimed. Standard trusted unittest lifecycle behavior is required for attribution;
custom runners cannot be assumed equivalent to it.

Ceilings: 128 files / 512 entries / depth 8 / 1 MiB per file / 8 MiB input / 16 MiB
derived, 64 discovered tests, 15 seconds worker wall / 10 seconds worker CPU /
512 MiB address space / 256 KiB per worker output file, 20 seconds overall, 8 KiB
packet. Defaults are 10 seconds wall and 5 seconds CPU. Input gaps, symlinks and
special files refuse execution. Worker CPU/memory/file limits are per process,
not aggregate descendant quotas. The worker gets a fresh process group; normal
completion and timeout kill remaining group members. A descendant that deliberately
detaches can escape that cooperative cleanup boundary. Other resources are not
sandboxed. Calls made only by child processes receive no credit.

Packet test-ID lists are truncated explicitly; full rows remain local. Logs are
bounded separately and are not embedded in the packet. No performance or token
savings claim. No scheduler, background job, Hermes/Kit integration or automatic
adoption.

## Reproduce the evidence

```sh
python -m unittest discover -s experiments/sentinel-exercise-0 -p test_exercise.py -v
python experiments/sentinel-exercise-0/demo.py --work /tmp/exercise-demo-new
python experiments/sentinel-exercise-0/demo.py --public-probe --work /tmp/exercise-public-new
```

The synthetic example starts with `validate(0)` incorrectly true. The real test
fails and is observed; the green decoy passes without entry. The demo author edits
`>= 0` to `> 0` between runs, then observes the real test passing. Each run has intact
checkpoint bytes and different source/code fingerprints. This demonstrates evidence
for an explicitly authored repair, not autonomous bug detection/repair.

The public probe executes the actual `operator_recipe.cell` function from public
ONECALL PR #4 commit `e723864c0cdad9ea2c86ee505d28bcbe679472aa`. Its exact source bytes
are retained in `fixtures/public/` and pinned to
`b4da1ae1c42e8654a3384b2ea971cc1663b193446872a8f07a9d75b6a6213dc1`.
Two new direct tests verify generated Python structure and shell argument
round-tripping, including quotes/metacharacters; one green decoy never enters cell.
Generated code is parsed, not executed: zero Hermes RPC/model calls. This is not
upstream subprocess-suite coverage or a test of the laptop caller.

Evidence folders retain packets, full results, manifests and original-byte
snapshots. `evidence/red.txt` precedes any implementation; `audit-red.txt` records
three additional failing adversaries against commit 8853518, before fixes. The
reproduction receipt identifies the final tested implementation and hashes. LENS
is loaded only if its SHA256 is
`a1c7e02ada1224a09327eaeee3b5d7d5c7f9e4b969f645ddc33725c49167d814`.

## Research and limits

Official sources checked for this implementation:

- [Python sys.setprofile](https://docs.python.org/3.12/library/sys.html#sys.setprofile): thread-specific call/return and C-call events; callback errors unset profiling.
- [Python unittest TestResult](https://docs.python.org/3.12/library/unittest.html#unittest.TestResult): lifecycle hooks and native success/failure/subtest semantics.
- [Python trace](https://docs.python.org/3.12/library/trace.html): native line counts/caller relationships, a useful alternative when those are the desired measurements.

This stdlib-only adapter adds selected-code/source binding, per-test context,
checkpoint integrity and a bounded evidence packet. It does not replace a coverage
engine. Optional coverage was absent; nothing was installed. Python 3.12.14 and
already-cached 3.14.8 were verified in cloud; current Sentinel laptop compatibility,
private-code behavior and operational usefulness remain unverified. Public synthetic
fixtures only. Unmerged experiment stacked on LENS PR #3. Rollback: remove this
experiment directory and its explicitly chosen derived outputs; no operator setup
or config was changed.
