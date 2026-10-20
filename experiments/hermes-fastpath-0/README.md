# FASTPATH-0: fewer model turns, the same checked operation

This is an inactive, cloud-tested recipe for one preauthorised operation:
inspect `settings.json`, change only `mode` from `draft` to `ready`, then verify
the exact final bytes and unchanged neighbours. Both paths run the same commands
through real Hermes at `8f817911723e3ec13e7f47fc022fdcc9e2149354`.

The baseline asks for three separate terminal tool calls. The fast path uses
the existing native `execute_code` tool and `hermes_tools.terminal` RPC to chain
those commands, check each result and stop on error. No custom daemon, gateway,
tool implementation, remote model account or operator installation is added.

## Reproduce

Prerequisites: Linux, Git, `uv` (observed 0.12.23), network access for public
setup, and a non-root user for the real permission-denial case. From this PR's
checkout with origin `https://github.com/woozyrabbit123/zenith-ai-lab.git`:

```sh
cd experiments/hermes-fastpath-0
python3 setup.py && .runtime/venv/bin/python -m unittest test_fastpath -v && .runtime/venv/bin/python run.py
```

Setup pins Python 3.14.8, upstream source and the upstream dependency lock. It
uses `--no-bin` and keeps the interpreter, venv, source, caches, native kernel
temporary directories and profiles under ignored `.runtime/`. Nothing is installed
globally or on an operator. The full runner writes `.runtime/results.json`.
Use `--case success --case disconnect --case verify_tamper` for a focused rerun.

`contract.json` was committed before implementation in `ded8092`; its SHA256 is
`d1905319d7b20814ca0c1d0fb25e3592a9bdec829483ac01e46179a7dcc92fa5`.
The detector imports neither the recipe nor Hermes. It inspects actual bytes,
counts atomic settings replacements with Linux inotify, and compares the
baseline/fastpath filesystem snapshots, including receipt bytes. An independent
test proves that duplicate same-content replacements are counted twice.

## Native invocation recipe

For a separately approved real host, first review/provision the request, state
directory and lock. The request binds the operation ID, canonical root, origin,
HEAD, full before/after file hashes and neighbour hash. `recipe.py` is standalone
stdlib source, restricted to this one exact operation. Inspect, update and verify
are invoked as:

```sh
/approved/python3.14 /reviewed/recipe.py inspect --request /approved/request.json
/approved/python3.14 /reviewed/recipe.py update --request /approved/request.json
/approved/python3.14 /reviewed/recipe.py verify --request /approved/request.json
```

To batch those same commands, use `fastpath.cell(commands)` with the reviewed
`[("inspect", command1), ("update", command2), ("verify", command3)]` list. It
returns the exact source for the model's supported tool shape:

```python
{"name": "execute_code", "arguments": {"code": cell(commands)}}
```

The generated cell imports `terminal` from native `hermes_tools`, calls it with
`timeout=10`, checks exit codes and JSON status, logs every internal step, and
prints a structured result. A failed step returns its full terminal error;
later commands do not run. It does not use `force`, set approval modes, directly
write files from the kernel, or retry an uncertain mutation blindly.

Version-dependent source: upstream `tools/code_execution_tool.py` generates the
terminal RPC stub and invokes `check_execute_code_guard`; `code_execution_rpc.py`
enforces enabled tools and call budget, strips blocked terminal parameters, and
dispatches through the ordinary tool handler. The experiment observes the real
native approval guard without changing its answer. A synthetic update-denial
policy is tested on both routes. Interactive/gateway approval prompting is not
tested; the fixture is already authorised and uses default headless policy.

## Recovery and correctness

A prepared receipt is atomically written before the settings replacement. The
update preserves permissions and changes only the one approved token. Actual
post-write verification is a separate command and advances the receipt to
`verified`. Requests with wrong cwd/origin/HEAD, wrong bytes, changed neighbours,
symlinks or foreign receipts are refused. Receipts and output use file/directory
fsync. A single-host advisory lock serialises cooperating recipe invocations.

On a repeated request, matching bytes plus a matching receipt allow a no-write
return; matching output without an owned receipt is refused. The injected
disconnect uses a real process exit after file replacement but before the next
receipt state. Recovery reconciles observed bytes with the prepared intent and
does not repeat the settings write. This proves the specified process-fault
case, **not OS-crash/power-loss safety or distributed exactly-once execution**.

Missing/tampered final files are injected outside the recipe, after its update,
and must fail verification. The update-failure case uses actual filesystem
permissions, not an invented successful write. All fixtures and requests are
synthetic and reset between baseline and fastpath.

## What the measurements mean

See `evidence/RESULTS.md` and `evidence/measurements.json` for observed counts.
The normal success uses four actual model responses in the baseline and two in
the fastpath, including the final answer. The same three terminal operations
remain; batching adds an outer `execute_code` dispatch. It does not reduce the
amount of necessary filesystem work.

Tool bytes returned to the model, cumulative tool-content bytes in requests,
and total serialised request bytes are counted separately. Native kernel/wrapper
overhead can make tiny tool outputs larger; early precondition failures save no
model turns. Reconciliation may repeat inspection and add an internal call.
Batching is unsuitable when a new approval or judgement is needed between steps,
or when output/errors cannot be safely handled by deterministic logic. Native
output truncation remains unchanged; this fixture does not hit its limit.

The loopback model deliberately scripts each plan; it does not demonstrate model
judgement or naturally choosing the recipe. Bytes are measured before path
normalisation and are not token/cost estimates. Stub token-usage fields are
placeholders. Wall times include startup, local HTTP, kernel and filesystem
overhead. **Model-turn reduction proven; real provider/operator speedup UNKNOWN.**

The actual Python agent/conversation/dispatch/kernel paths run. CLI boot,
gateway, Telegram, Desktop, ACP, live models, real operator callers and other
OSes are untested. One author produced implementation and detector; independent
peer review remains pending. No CI run or installed capability is claimed.

`adoption.json` disables installation and activation. Future host use needs its
own explicit approval, compatibility and approval-flow checks, reviewed paths
and one real caller test. A new operation needs a newly reviewed contract.
Rollback: stop using the recipe, retain/reconcile pending receipts, and restore
before bytes only after checking current after hash and obtaining authorisation.
Do not blindly undo concurrent edits. Cloud teardown: remove this experiment's
`.runtime/`; no operator rollback is currently needed.

Upstream Hermes remains MIT in the fetched checkout. This repository has not
selected a licence for its own new code; no upstream code is vendored here.
