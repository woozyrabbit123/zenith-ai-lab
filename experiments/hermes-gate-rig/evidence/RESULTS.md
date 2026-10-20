# Observed real-loop results

**Rig: TESTED-REAL-LOOP. Gate: PARTIAL / UNSAFE, inactive.**

Tested implementation commit: `5f656a6ae979330b43a0c508e9421aa44f927170`. Upstream: `8f817911723e3ec13e7f47fc022fdcc9e2149354`.

All 27 cases matched the contract frozen in `7330da0`; this includes 13 reproduced unsafe gaps, 12 scoped enforcement/allowed cases, one absent control and one scripted recovery. These are case counts, not independent bug counts or security certification.

Five focused self-check methods passed. Three additional upstream helper checks observed dispatcher exception pass-through at both paths and shallow-merge/later-override semantics. The two fault checks execute real helpers with an injected exception; they do not execute a downstream tool.

| Case | Classification | Configured in fixture | Registered | Invoked | Tool dispatches | Observed changed sentinel |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| absent_wrong | control | 0 | 0 | 0 | 1 | wrong/out.txt |
| prefix_wrong | enforced | 1 | 1 | 1 | 1 | none |
| prefix_allowed | enforced | 1 | 1 | 1 | 1 | allowed/out.txt |
| veto_wrong | enforced | 1 | 1 | 1 | 0 | none |
| unapproved | known_gap | 1 | 0 | 0 | 1 | wrong/out.txt |
| safe_mode | known_gap | 1 | 0 | 0 | 1 | wrong/out.txt |
| crash | enforced | 1 | 1 | 1 | 0 | none |
| timeout | enforced | 1 | 1 | 1 | 0 | none |
| empty | known_gap | 1 | 1 | 1 | 1 | wrong/out.txt |
| object | known_gap | 1 | 1 | 1 | 1 | wrong/out.txt |
| malformed | enforced | 1 | 1 | 1 | 0 | none |
| lookalike | enforced | 1 | 1 | 1 | 1 | none |
| ssh_origin | enforced | 1 | 1 | 1 | 1 | ssh/out.txt |
| missing_origin | enforced | 1 | 1 | 1 | 1 | none |
| multiple_origin | enforced | 1 | 1 | 1 | 1 | none |
| workdir_override | enforced | 1 | 1 | 1 | 1 | none |
| write_file_escape | known_gap | 1 | 1 | 0 | 1 | wrong/out.txt |
| patch_escape | known_gap | 1 | 1 | 1 | 3 | wrong/out.txt |
| cd_escape | known_gap | 1 | 1 | 1 | 1 | wrong/out.txt |
| python_escape | known_gap | 1 | 1 | 1 | 1 | wrong/out.txt |
| heredoc_escape | known_gap | 1 | 1 | 1 | 1 | wrong/out.txt |
| subshell_escape | known_gap | 1 | 1 | 1 | 1 | wrong/out.txt |
| absolute_escape | known_gap | 1 | 1 | 1 | 1 | wrong/out.txt |
| git_c_escape | known_gap | 1 | 1 | 1 | 1 | wrong/git-config-marker |
| linked_worktree | enforced | 1 | 1 | 1 | 1 | linked/out.txt |
| second_hook_override | known_gap | 2 | 2 | 2 | 1 | wrong/out.txt |
| recovery | recovery | 1 | 1 | 2 | 2 | allowed/out.txt |

The absent control wrote the wrong-repo sentinel once. The matching prefix case dispatched the terminal, returned exit 97 and left the sentinel absent. The veto control dispatched no tool. Recovery first refused in the wrong repo, then corrected workdir and wrote exactly 17 bytes once. Expected output SHA256: `5ae3ebfa2655d3db1626b245e1679c458ba0e779c2ddb6c7715bfa1ebf41de42`.

The fresh-worktree command installed 67 packages from the pinned lock, ran five self-checks and reproduced the full matrix. Semantic outcomes matched the final-source run. See `reproduction.json` for exact refs and the separately tested bootstrap-only correction. This was same-author reproduction, not independent peer review.

`results.json` contains the final-source hashes, tool results, forwarded dispatch arguments, hook audit, metadata probes and independently inspected sentinel bytes/hashes. `runtime.json` pins the dependency-lock hash and observed installed versions. `bootstrap-containment.json` records a fresh --no-bin install check after removal of the task-created cloud user-bin launcher.

Case timings are wall time including process startup, local HTTP and fixture overhead; no model/operator speedup is inferred. No CI run is claimed. The Actions-permissions endpoint returned 403 to the available integration; no workflow or paid runner was added.

UNTESTED: CLI boot path, gateway, Telegram, Desktop, ACP, kanban, delegated children, live provider/model judgement, real operator installation, other OSes. See ../README.md and ../adoption.json.
