# Candidate impact of engine.validate

Review `pipeline.run`, then candidate test `test_flow.test_good`. The first calls `check(x)`, an import alias for `engine.validate`; the second calls `launch(1)`, an import alias for `pipeline.run`. Name grep misses the test call.

These are syntactic candidates, not runtime reachability or coverage proof. No project code or tests were executed. UTF-8/CRLF source bytes stayed unchanged.

[Exact call-site evidence](derived/report.json) · [full graph](derived/graph.json)
