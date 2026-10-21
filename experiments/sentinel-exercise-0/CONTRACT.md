# EXERCISE-0 frozen contract

`exercise.py run --root APPROVED_TRUSTED_TEST_ROOT --target file.py:qualified_name
--out NEW_DERIVED [--pattern test_*.py]` runs trusted unittest code, not an arbitrary
untrusted-code sandbox. New tracked changes only here; reuse hash-pinned LENS read/
inventory helpers from PR #3. No target/operator installation, model/API or service.

Select one compiled code object by source-relative .py path and exact co_qualname;
reject ambiguous/missing targets. Bind observations to source SHA256, first line,
qualified name and stable bytecode/constants signature. Same-name code in another
file and substituted code must not count. Compiling target source is not executing
it; tests/discovery DO execute caller-approved project code in a resource-limited
child. No claim of filesystem/network isolation or malicious-test resistance.

Observe Python main-thread call events under TestResult startTest/stopTest context.
Discovery/class-hook calls remain unassigned, never credited to tests. Report every
test's actual PASS/FAIL/ERROR/SKIP/XFAIL/XPASS/subtest outcome and event count. Main-
thread setup/teardown calls are included. Generator resumes can be call events.
Absence is NOT_OBSERVED_IN_SCOPE, never uncovered/dead/safe. Observation does not
prove assertion quality, correctness, line/branch coverage or other-thread/process
execution. Profiler changes/code mismatch invalidate clean observation proof.

Bounded finite root snapshot (including regular data files), original source/data
hash and inventory recheck after tests; target/source mutation cannot yield clean
proof. Persist local manifest, full result, bounded logs; compact JSON <=8 KiB.
No raw test stdout/stderr in packet. Output fresh/separate; refuse symlinks, special
files, path traversal, unreadables, incomplete root or pre-existing output before
executing tests. No implicit ignores; choose a bounded source/test scope.

Ceilings: 128 files, 512 entries, depth 8, 1 MiB/file, 8 MiB input, 16 MiB derived,
64 tests, 15s worker wall, 10s worker CPU, 512 MiB address space, 256 KiB per worker
file, 20s overall. Defaults worker wall 10s/CPU 5s. No child started after input
scope refusal. Test cap checked after discovery but before any test body. Deadline,
missing result, log overflow, source mutation or instrumentation loss => INCOMPLETE
or FAIL, never clean OBSERVED. Full summaries can exceed packet; omissions explicit.

RED before code. Independent tests: aliases/dynamic method calls, green decoy,
discovery-only calls, same-name false positives, failures/subtests/skips/xfail,
mutation, code replacement, profiler disable, source/symlink/traversal, test/time/
output caps, target ambiguity and packet bounds. Synthetic regression example,
actual public-source test probe, Python 3.12/cached 3.14 and fresh worktree proof.
