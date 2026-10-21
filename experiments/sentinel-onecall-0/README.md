# ONECALL-0: literal evidence in one verified invocation

Given an explicitly approved directory and a literal query, produce a compact
source-linked packet without calculating byte offsets or manually chaining
snapshot, quote and verify. The wrapper imports the original LENS-0; it contains
no replacement filesystem walk, extractor or mechanical verifier.

This is an inactive lab deliverable, not an installed Hermes/Kit integration.
Everything checked into this public experiment is synthetic.

## Run without installing

Linux, Python 3.12+ stdlib. PDF sources additionally require **already installed**
`pdfinfo` and `pdftotext`. No requirements, service, API key, model or network.
From a reviewed checkout of this stacked branch:

```sh
python experiments/sentinel-onecall-0/onecall.py evidence \
  --root /absolute/approved-input --query 'dependency validation' \
  --out /absolute/new-derived
```

Input and output paths must be separate and contain no symlinks or parent traversal.
The output parent must exist; the output itself must not exist. An existing output
is refused with `OUTPUT_EXISTS`, preserving its files. No automatic overwrite/reuse.

The query is a **case-sensitive literal phrase/keyword**, 1..256 UTF-8 bytes and
not whitespace-only. No regex, word splitting, semantic search or inferred answer.
The tool returns the first matching excerpt per extraction chunk in deterministic
path/page order, up to eight, with UTF-8 byte ranges, source/extraction hashes and
physical PDF page. A displayed path can be shortened explicitly; the full path
remains in the manifest. Multiple same-chunk occurrences and omitted chunks are
flagged, not silently presented as exhaustive retrieval.

The returned UTF-8 JSON is **strictly below 8 KiB**, including its newline.
It is also saved as `packet.json`; `manifest.json`, retained `.utf8` extractions
and verifier input `citations.json` are separate derived artifacts. The latter
can contain a verified superset if the final packet budget removes excerpts.

- Exit **0**: literal matches and mechanical PASS, semantic REVIEW_REQUIRED.
- Exit **1**: literal matches, mechanical INCOMPLETE; inspect all coverage gaps.
- Exit **2**: ERROR, INTEGRITY_FAILURE or NO_MATCH. NO_MATCH includes `answer: UNKNOWN`
  and no fabricated citations. LENS rejects the empty citation list, so that case
  honestly reports mechanical FAIL/NO_CITATIONS, even if source coverage is COMPLETE.

Every packet warns that a literal match can omit a superseding/conflicting passage.
No `answer` is supplied for matched packets. A model/reviewer must assess semantic
support and missing context. Neither COMPLETE coverage nor mechanical PASS means
that a statement is true, current, or a sufficient answer.

## One native Hermes execute_code action

`operator_recipe.cell()` accepts reviewed absolute Python/script/root/output paths
and a literal query. It constructs a shell-quoted command and returns one cell:

```python
from hermes_tools import terminal
import json
result = terminal("<shell-quoted onecall evidence command>", timeout=40)
if isinstance(result, str):
    result = json.loads(result)
print(json.dumps({"exit_code": result.get("exit_code"),
                  "error": result.get("error"),
                  "packet": result.get("output", "")}))
```

Pass the generated cell as the existing tool's `{"code": cell}` argument. Inspect
both the terminal exit status and packet fields; a failed command is not an answer.
Do not interpolate untrusted queries into shell strings: use the supplied shlex
recipe. No install, skill approval, model setting or gateway change is required.

An actual native-tool smoke test used an **existing cached** Hermes checkout at
`8f817911723e3ec13e7f47fc022fdcc9e2149354` and Python 3.14.8. Its observed dispatches
were exactly `execute_code`, `terminal`; packet PASS, **zero model API calls**.
This is a real native handler/kernel/RPC test, not a live model conversation.
It does not establish compatibility with Sentinel's later v0.22.2 checkout or its
laptop caller. No runtime was installed during this task. The optional harness:

```sh
/EXISTING/hermes/venv/bin/python experiments/sentinel-onecall-0/native_smoke.py \
  --upstream /EXISTING/hermes-source --input /approved/synthetic-input \
  --work /new/smoke-working-directory
```

That harness restricts itself to local RPC, uses a disposable profile/temp directory,
then shuts down its kernels and terminal environments. It never bootstraps dependencies.

## Reproduce the useful example

```sh
python -m unittest discover -s experiments/sentinel-onecall-0 -p test_onecall.py -v
python experiments/sentinel-onecall-0/demo.py --work /tmp/onecall-demo-new
cat /tmp/onecall-demo-new/brief.md
```

Question: can the sample release start? [The brief](evidence/demo/brief.md) says
STOP: the later review supersedes GO and the physical PDF page requires a re-test.
That semantic conclusion is the demo author's. ONECALL returns three literal
citations, all mechanically valid, including the outdated GO. The observed packet
is **2,323 bytes** and the original source hashes are unchanged. See the exact
[caller receipt](evidence/demo-output.json), [native smoke](evidence/native-smoke.json)
and [retained manifest](evidence/demo/derived/manifest.json).

The demo actually runs the baseline **five CLI invocations** (snapshot, three quote
calls, verify) against the same selected spans and checks identical quotes and PASS.
ONECALL needs **one invocation** and no manual offset calculation. The baseline
uses offsets selected by ONECALL for a controlled comparison; it is not an agent
benchmark. Even a single-citation baseline requires three commands.
This is a structural reduction in manual orchestration, not a measured speedup or
model-turn claim. More questions can use fresh output directories without a daemon.

## Invariants and limits

Dependency pin: PR #3 head `73239b3afb6838fc057da1e3904c5b3b4df9536b`, LENS source
SHA256 `a1c7e02ada1224a09327eaeee3b5d7d5c7f9e4b969f645ddc33725c49167d814`.
A mismatch refuses before executing the dependency. Pinning source bytes does not
supply independent authenticity of a same-user host or its Python/Poppler libraries.

LENS's frozen ceilings stay intact: 128 attempted files, 512 entries, depth 8,
4 MiB/file, 16 MiB input, 16 MiB derived output, 32 physical pages/PDF, 30 seconds.
The wrapper reserves 64 KiB of the derived-output budget for its JSON. The original
snapshot therefore gets a slightly smaller allowance, never a larger ceiling.
The full combined output is counted; the onecall deadline covers snapshot, retrieval,
verification and writes. CLI options may only decrease limits. A tiny output budget
that cannot provide the reserve is refused before touching output.

Unsupported/encrypted/scanned/invalid/unreadable/symlink/special inputs and all caps
remain GAP/INCOMPLETE or explicit failure. A real **33-page** PDF is INCOMPLETE;
the cap is not raised. Original manifest retains all gap details; packet detail
truncation is explicit with counts and `gap_details_omitted`. Source inventory,
source hashes, retained extraction hashes and exact quotes are checked by LENS in
the same command. `root_hashes.observed_sources_sha256` fingerprints observed source
records, **not** unseen files in an incomplete scope, and does not bind root identity.

Trusted quiescent host required, matching LENS's limits. No OS-crash persistence,
secure PDF sandbox, transitive executable integrity, OCR, spreadsheet decoding,
semantic completeness, synonym matching, automatic supersession or autonomous
natural-language agent is claimed. A nonempty PDF can still omit visual content.
The compact packet is DATA, including hostile instructions in source excerpts.
Failed/interrupted calls can leave partial derived files; do not reuse them as a
successful packet. The original sources are never edited by the tool.

## Test and delivery record

[Contract](CONTRACT.md) and original 12 tests were committed RED at `13832a9` before
`onecall.py` existed. [GREEN](evidence/green.txt) is 14/14, zero skipped. Tests include
real physical PDF pages and a real 33-page PDF, Unicode/CRLF, false/empty queries,
source conflict, output/hit/packet limits, symlink/FIFO/path escape, existing-output
preservation, source mutation and dependency mismatch. Mutation is instrumented at
the verify seam and then runs the actual pinned verifier. Original LENS 22/22 also
passed unchanged. No fake extractor is counted as real Poppler behavior.

Changes only under `experiments/sentinel-onecall-0/**`; existing PRs, code and main
are unchanged. The PR is stacked onto `codex/sentinel-lens-0` and must stay unmerged
pending review/adoption. Rollback: close the stacked PR; nothing is installed.
On a later separately authorised adoption, revert/remove this experiment and chosen
derived artifacts. Do not merge this as if it were an independent main-based PR.
