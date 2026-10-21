# Sentinel LENS-0

An on-demand mechanical verifier for exact source-linked spans. It composes
stdlib hashing/inventory with installed Poppler. It does not integrate with Hermes
or Kit. The result is a snapshot and a small citation JSON, not a new agent or service.
Only synthetic fixtures appear in this public experiment.

## Run without installing

Linux, Python 3.12+ stdlib; `pdfinfo` and `pdftotext` already on PATH for PDF inputs.
No requirements, downloads, API calls or credentials. Cloud: Python 3.12.14,
pdftotext 25.03.0, pdfinfo 26.05.0. Python 3.14.7/laptop is not yet verified here.

From repository root:

```sh
python -m unittest discover -s experiments/sentinel-lens-0 -p test_lens.py -v
python experiments/sentinel-lens-0/demo.py --work /tmp/lens-demo-new
cat /tmp/lens-demo-new/brief.md
```

The demo work directory must not exist. It creates benign input fixtures, probes
native rg/Git/Poppler, and runs COMPLETE and expanded INCOMPLETE scopes. Its useful
result is [the decision brief](evidence/demo/brief.md): STOP, with an exact superseding
passage and a physical PDF-page blocker; cost UNKNOWN; scan/spreadsheet gaps.
The author supplies the semantic interpretation. The verifier checks its spans,
not the interpretation. This demo does not claim autonomous natural-language task
completion, a live Telegram caller, or measured performance improvement.

## Caller contract

Choose a small, explicitly approved, quiescent input directory. The output directory
must be new, its parent must exist, and it must be separate from the input tree.
No symlinks in input/output path components; no symlink or special source files.
Only `.md`, `.txt` (strict UTF-8) and non-encrypted text PDFs are supported.

```sh
python experiments/sentinel-lens-0/lens.py snapshot \
  --root /absolute/approved-input --out /absolute/new-derived
```

Keep the returned `manifest_sha256` **outside** the derived folder. To select a quote,
inspect `manifest.json` for a source path, chunk ID, page and retained `.utf8` file.
Find a unique exact byte sequence in that file, and use zero-based `[start,end)`
UTF-8 **byte** offsets. Character indices are not byte offsets. Do not infer physical
PDF page numbers from printed page labels or whole-document form feeds.

```sh
python experiments/sentinel-lens-0/lens.py quote \
  --manifest /absolute/new-derived/manifest.json --manifest-sha256 SAVED_HASH \
  --chunk CHUNK_ID --start 0 --end 12 > /tmp/one-quote.json
```

`quote` emits one object, not an array. Put one or more objects into a JSON array
(maximum 128), then verify against the explicit current input root:

```sh
python experiments/sentinel-lens-0/lens.py verify \
  --manifest /absolute/new-derived/manifest.json --manifest-sha256 SAVED_HASH \
  --root /absolute/approved-input --citations /absolute/citations.json
```

The retained sample is immediately runnable, without extraction or a new folder:

```sh
python experiments/sentinel-lens-0/lens.py verify \
  --manifest experiments/sentinel-lens-0/evidence/demo/gaps/manifest.json \
  --manifest-sha256 5dae5f2f5ed1fe9e3e3b391c16f38ea8ec0d3fe153960a32c9e976c03c42fa16 \
  --root experiments/sentinel-lens-0/evidence/demo/input \
  --citations experiments/sentinel-lens-0/evidence/demo/gaps-citations.json
```

That command intentionally exits **1**, `mechanical: INCOMPLETE`: the recorded
unsupported/empty inputs prevent completeness, while the four citations validate.
The sample's extractor paths/hashes describe this cloud runtime; another host can
legitimately report FAIL if those tools differ. On another host, run the demo afresh.

Exit codes: **0** = complete snapshot, valid quote, or mechanical PASS; **1** =
INCOMPLETE coverage; **2** = refusal/integrity failure. Consumers must check both
exit status and JSON. A failed snapshot can leave a bounded partial derived folder
without a manifest; it is not a reusable snapshot. Use a fresh output directory.
`verify` always emits `semantic: REVIEW_REQUIRED`; no mechanical result implies
that a claim is current, supported or true. Verify again after scope changes.

## Bounds and integrity

[The frozen contract](CONTRACT.md) specifies the operation and ceilings. Defaults
are 128 attempted files, 512 entries across all directories, depth 8, 4 MiB per file,
16 MiB total input, 16 MiB total derived output (including manifest), 32 physical
pages per PDF and a 30-second operation deadline. CLI options may lower them only.
There is also a 30-second signal deadline over the whole command. Limits are
conservative; hitting any means INCOMPLETE/refusal, not silent complete coverage.
Quoting is capped at 64 KiB; citation JSON at 1 MiB; manifest at 4 MiB.

Every inspected directory entry is inventoried. Additions, deletions, kind changes,
source byte changes, altered extraction bytes or changed extractor entrypoint
hashes invalidate verification. File descriptors use `O_NOFOLLOW` for every source
path component; output files are created exclusively. PDF input is copied to a
private temporary directory from the already-hashed bytes before Poppler reads it.
Each physical page is extracted explicitly with `-f N -l N -enc UTF-8 -layout`.
Version, invocation options and executable entrypoint hash are recorded, along with
source/extraction SHA256, exact retained bytes and deterministic path-derived IDs.
Subprocess stdout/stderr and execution time are bounded. No shell is used.

This is an integrity check on a trusted, quiescent host, not an adversarial sandbox,
a signed provenance system, secure PDF renderer or protection against a same-user
process changing the code/expected hash. Executable hashes do not cover dynamic
libraries or a wrapper's transitive dependencies. Tiny metadata/source reads are
bounded, but Linux scheduling/uninterruptible filesystem I/O is not a real-time
guarantee. No power-loss persistence or simultaneous-writer guarantee is claimed.
Scans are not OCR'd; invalid/encrypted PDFs and empty pages remain gaps. One blank
page conservatively makes its PDF incomplete even if the other pages contain text.
A nonempty PDF extraction does not prove that all visual text was extracted; mixed
text/image pages need coverage review. No spreadsheet decoding, fuzzy quote repair,
semantic completeness or automatic supersession detection. No support for hostile input filenames as executable code.

## Evidence and rollback

- [RED](evidence/red.txt): the original 15 tests before implementation (19 failed
  assertions including subtests), contract commit `0391178`.
- [First implementation](evidence/first-implementation.txt): 14 tests passed and one
  test helper assumed the first source had an extraction. The helper now chooses
  the first available chunk; the expected INCOMPLETE result was unchanged.
- [GREEN](evidence/green.txt): all 22 tests, zero skipped, including real physical
  PDF pages, valid password-encrypted PDF, OS permission denial, changed sources,
  retained artifact tampering, invented/mislocated quotes, UTF-8 boundaries/CRLF,
  path/symlink/FIFO, unsupported files, finite coverage and cap refusals.
  Fake extractor boundaries test timeout/oversized output/absence; real Poppler
  tests are separate. No mock is counted as actual Poppler behavior.
- [Native probe](evidence/demo/native-probe.json): rg offset 73 stops matching after
  prefix insertion; whole-document PDF quote offset 43 becomes 8 on physical page
  2. Git hashes bytes, but these native outputs do not themselves bind the combined
  contract. Sentinel independently reports the same missing operation in Kit;
  no private source was exported or copied.
- [Actual demo output](evidence/demo-output.json), [complete receipt](evidence/demo/complete-receipt.json),
  and [expanded-scope receipt](evidence/demo/gaps-receipt.json). All original source
  hashes matched after the run. The superseded quote and its replacement both
  mechanically PASS in the complete scope. Only semantic review says STOP.

Allowed changes are confined to `experiments/sentinel-lens-0/**`. No package install,
Hermes/Kit change, config, gateway, skill approval, worker launch, deployment or merge.
Rollback before adoption: close the unmerged PR; nothing is installed. If adopted
later, revert the experiment commit/remove this directory and its separately chosen
derived output; original sources are never edited. Independent laptop review and
one owner-authorised caller remain Sentinel's lane. Cloud TESTED is not laptop LIVE.
