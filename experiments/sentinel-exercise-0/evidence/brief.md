# Measured EXERCISE-0 demonstration

| Run | Test suite | Credited test | Passing decoy | Integrity | Packet bytes |
| --- | --- | --- | --- | --- | --- |
| Synthetic buggy boundary | FAIL | test_boundary | no entry | PASS | 1023 |
| Synthetic authored fix | PASS | test_boundary | no entry | PASS | 1010 |
| Actual public recipe | PASS (3 tests) | 2 direct tests | no entry | PASS | 1086 |

The demo author changed `>= 0` to `> 0` between runs. Each independent run retained
its exact input bytes; both source and compiled-code fingerprints changed between
runs. This is an explicitly authored repair, not autonomous repair or a coverage
claim. The real test checks the boundary; the decoy only asserts True.

The public probe executes the exact public `operator_recipe.cell` source from
ONECALL commit `e723864c0cdad9ea2c86ee505d28bcbe679472aa` with two new trusted direct tests.
Generated Python is parsed, not executed. The tests check one terminal call and
argument round-tripping with quotes/metacharacters. Zero Hermes RPC or model calls.
Three discovered tests pass; only the two calling cell receive entry credit.

The compact reports retain no raw source or stdout; full local artifacts here are
public/synthetic only. No laptop/current Hermes, integration, performance, test
assertion quality, branch/line coverage or safe-to-edit claim. Results are scoped
to main-thread Python call events in unittest contexts. See README for limits.
