# HOOK-RIG-0: real Hermes dispatch, observable effects

This experiment runs the actual `run_agent.AIAgent.run_conversation` entry point
at upstream `8f817911723e3ec13e7f47fc022fdcc9e2149354`, with a deterministic
loopback OpenAI-compatible scripted server. No remote LLM, account token or
operator machine is involved. It tests a constrained terminal hook and records
its limitations. **PARTIAL / UNSAFE for installation.** The reusable result is
the execution rig; the terminal tripwire is not a security boundary.

## Reproduce

Prerequisites: Linux, Git, `uv` on PATH, network access for public source and
package setup. Observed uv version: 0.12.23. Start in a clean clone of
`https://github.com/woozyrabbit123/zenith-ai-lab` on this PR's branch.

```sh
cd experiments/hermes-gate-rig
python3 setup.py && .runtime/venv/bin/python -m unittest test_rig -v && .runtime/venv/bin/python run.py
```

Setup refuses the wrong lab origin, fetches the exact upstream commit, installs
Python 3.14.8 and uses upstream's locked dependencies with no optional/dev groups.
The interpreter install uses `--no-bin` so uv creates no user-level launcher.
Everything installed or generated is under ignored `.runtime/` in this experiment.
No global packages, shell configuration or operator hooks are installed. An
initial Python/uv installation is a prerequisite, not silently performed.

The full command prints each case and writes `.runtime/results.json` including
sanitised tool results, dispatch arguments, hook invocations and filesystem hashes.
For a focused reproduction:

```sh
.runtime/venv/bin/python run.py --case absent_wrong --case prefix_wrong --case prefix_allowed --case recovery
```

Each case uses a fresh synthetic Git/profile workspace. The worker's process cwd
differs from the terminal task cwd. Local model-metadata probes are recorded
separately and cannot consume scripted conversation turns. Each process has a
55-second deadline. The workers receive a small environment allowlist without
account/provider credentials; Python socket connections are restricted to
loopback. This is isolation for these reviewed fixtures, not an OS sandbox for
untrusted code. Shell subprocesses are not network-sandboxed by that Python fence.

## What is checked

`contract.json` was committed before candidate implementation in `7330da0`.
Its SHA256 is
`5b82c92343127078a18eee9c81806fd2dacefad8927f44f24cffdb7ed57c148b`.
`verify.py` refuses changed contract bytes. Expected filesystem effects come
from that file, not the candidate, model's “done”, or reference implementation.
It checks exact output bytes to catch duplicate effects as well as missing ones.
The absent-gate wrong-repo control must actually write before guarded claims are
accepted. See `evidence/` for observed results and scope counts.

The real loop, terminal and file tools are upstream code. `worker.py` observes
the real `model_tools.handle_function_call` boundary and forwards calls unchanged.
Its post-tool observer contributes no policy directive. “Dispatch” means crossing
that observed boundary, not successful shell execution. Counts and actual
filesystem changes are reported separately. Storage verification covers the named
sentinel files and synthetic Git config marker, not an exhaustive filesystem audit.
This uses the public Python agent entry point, **not a tested CLI command or
gateway boot/registration sequence**.
Registration is explicitly invoked through upstream `register_from_config` with
consent only for the disposable profile.

Two mechanisms are deliberately distinct:

- **Veto:** block all matching terminal calls before tool dispatch; this is a
  control, not a claim that payload cwd identifies the terminal session.
- **Prefix:** modify `command` to check the actual initial shell cwd's origin
  then exit 97 on mismatch. A refused prefix call still dispatches the terminal.
  The partial modify preserves `workdir`, timeout and other top-level parameters.

The prefix covers every terminal command in its initial cwd, including reads;
it does not classify arbitrary shell text as read-only or mutating. Supported
origin forms are exact GitHub HTTPS and Git SSH identities (case folded), with
one raw fetch URL and at most one matching push URL. Missing, multiple, malformed
or look-alike origins are refused. This checks metadata, not ownership, expected
HEAD, trusted repository contents, or effective `insteadOf` transport routing.

## Important limits

Known gaps are intentionally reproduced as findings, not counted as security
successes. A matching expected gap means the rig detected unsafe behaviour.
Unapproved/safe-mode hooks can be absent. Exit-zero empty/`{}` responses allow
execution. Independent file tools bypass a terminal-only matcher. A later
modify hook can replace the guarded command. Commands can change directory or
write elsewhere after the initial cwd check. Fault injection directly executes
both upstream dispatch helpers and observes their exception pass-through; those
helper tests do not claim an end-to-end exploit or downstream write.

The scripted model proves execution mechanics, not a model's judgement or
ability to choose recovery. The recovery sequence is scripted and verifies
refusal, corrected workdir, one exact output and dispatch counts. No live model,
CLI startup, gateway, Telegram, Desktop, ACP, kanban, delegated child, installed
operator or Windows/macOS behaviour is established. No speed improvement is
claimed. Reported case wall times include startup and test overhead.

The same author built the candidate and verifier. The frozen earlier contract,
raw receipts and separate storage checks improve auditability but do not replace
independent peer review. No CI enforcement is claimed. The available GitHub
integration denied the Actions-permissions endpoint; no workflow or paid runner
was added. A reviewer can rerun the command at a pinned candidate commit and
compare the original contract commit before trusting the evidence.

`adoption.json` is an **inactive manifest**, not an installer. Rollback/teardown:
delete this experiment's `.runtime/` to remove its source checkout, interpreter,
venv, caches and disposable fixtures. Revert/remove this experiment to remove the
artifact. Nothing is installed on an operator host.

Upstream Hermes is MIT; its source and licence remain in the fetched checkout.
This repository has not selected a licence for its own new code. No upstream
implementation is vendored or relicensed here.
