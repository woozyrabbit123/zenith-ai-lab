# Observed FASTPATH-0 result

Implementation tested at `02ae67c88d0b3292029ed6ae2365196ad9ce3c68` against upstream `8f817911723e3ec13e7f47fc022fdcc9e2149354`.

**TESTED-CLOUD / REAL-LOOP. Inactive; no live operator/provider speed claim.**

Ten paired cases ran twenty actual Hermes conversations. All frozen expectations matched, and baseline/fastpath monitored filesystem bytes (including receipt) matched in every pair. Five focused self-checks passed. Success, tamper detection and disconnect recovery were reproduced in fresh fixtures/sessions after the complete run.

| Case | Baseline → fastpath model responses | Baseline → fastpath dispatcher entries | Settings replacements each | Observed status |
| --- | ---: | ---: | ---: | --- |
| success | 4 → 2 | 3 → 4 | 1 | verified |
| wrong_cwd | 2 → 2 | 1 → 2 | 0 | refused |
| wrong_repo | 2 → 2 | 1 → 2 | 0 | refused |
| precondition | 2 → 2 | 1 → 2 | 0 | refused |
| update_failure | 3 → 2 | 2 → 3 | 0 | update_failed |
| verify_tamper | 4 → 2 | 3 → 4 | 1 | verify_failed |
| verify_missing | 4 → 2 | 3 → 4 | 1 | verify_failed |
| repeat | 7 → 3 | 6 → 8 | 1 | verified |
| disconnect | 5 → 3 | 4 → 7 | 1 | verified |
| terminal_denied | 3 → 2 | 1 → 3 | 0 | policy_refused |

For normal success:

- Model responses: 4 → 2, including the final answer.
- Terminal calls remain 3 → 3; batching adds one outer execute_code dispatch.
- Unique tool-content bytes returned to the model: 508 → 710 (larger).
- Total serialised model-request bytes: 65557 → 33266 (not token/cost estimates).
- Measured local fixture wall time: 6.98 s → 8.1 s; no live provider involved and no speedup inference.

Batching is worse on early scope/precondition failures: model responses stay 2 → 2 while an outer dispatch and wrapper payload are added. On disconnect recovery it uses an extra internal inspection (four baseline terminal calls versus five batched terminal calls) to reconcile safely. Do not batch operations that require new human approval or model judgement between steps.

The kernel watcher counts atomic settings replacements independently of the recipe. It observed one replacement for success, repeated invocation and process-disconnect recovery; zero for scope/precondition/update/policy failures. Tamper/deletion was injected outside the recipe after update and verification refused success. The receipt stayed applied rather than verified. The update-failure case used a real non-writable fixture directory and retained a prepared intent.

The native execute_code approval function was observed without changing its decision; the preauthorised headless fixture allowed it. A synthetic terminal update veto remained effective through both dispatch routes. Interactive/gateway human confirmation is untested. Dispatcher counts refer to model_tools.handle_function_call entry; a veto can occur before that boundary for a normal call and within it for RPC. Entry is not proof an action ran; filesystem observation decides effects.

Receipts/files/directories use fsync, but only explicit process termination after file replacement was tested. No OS/power-loss or distributed exactly-once guarantee. Detection and implementation share an author; independent review remains pending. Full raw transcripts are generated under ignored .runtime/; measurements.json retains compact measured metrics, filesystem bytes/hashes, step results, approval observations and exact source hashes.

No CLI/gateway/Desktop/Telegram/ACP, actual operator, live model or other OS proof. No CI run, install or peer dispatch. Model-turn reduction proven; real speedup UNKNOWN.
