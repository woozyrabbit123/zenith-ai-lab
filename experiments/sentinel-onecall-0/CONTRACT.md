# ONECALL-0 contract (frozen before implementation)

`python onecall.py evidence --root ALLOWED --query LITERAL --out NEW_DERIVED`

One local command imports the exact hash-pinned LENS-0 implementation from PR #3
head 73239b3afb6838fc057da1e3904c5b3b4df9536b, calls its snapshot, selects literal
UTF-8 byte hits, then calls its verifier in the same workflow. No copied extraction,
filesystem walk or alternate verifier. No packages/network/model/installation.
Only experiments/sentinel-onecall-0/** changes; stacked PR leaves PR #3 unchanged.

- Case-sensitive literal phrase or keyword; 1..256 UTF-8 bytes, non-whitespace.
  No regex, semantic search, token splitting, query execution or inferred answer.
- Existing LENS file/entry/depth/byte/page/time ceilings remain ceilings. Reserve
  64 KiB from the derived-output allowance for wrapper JSON. All original gaps
  persist in the manifest. CLI caps may only decrease; default operation <=30 s.
- Reject parent traversal before normalising caller paths. All source and output
  access stays with LENS's no-follow rules. Output must be fresh and separate;
  output-dir-exists is explicit and must not overwrite anything.
- At most 8 citations, at most 384 UTF-8 bytes/excerpt, one first occurrence per
  extraction chunk. Deterministic path/page ordering. Additional hits/packet budget
  omissions are explicit; source coverage and retrieval coverage are separate.
- Each citation includes source ID/path, source/extraction SHA256, physical page
  or null, chunk ID, zero-based UTF-8 byte [start,end), and exact excerpt bytes.
  Paths displayed in the compact packet may be shortened with an explicit flag;
  the exact path is retained in the manifest. Boundaries never split UTF-8.
- Same-workflow LENS verification is mandatory, including source integrity and
  the generated citations. Return <8192 UTF-8 JSON bytes and persist that identical
  packet, citation JSON and full original LENS manifest/extractions separately.
  Hash the exact manifest and observed source set. Never relabel an integrity FAIL
  as PASS. NO_MATCH => UNKNOWN/no answer and no invented citations; original LENS
  verifier rejects an empty citation list, so mechanical FAIL with NO_CITATIONS is
  explicit. Coverage may still be COMPLETE: searched sources had no literal hit.
- Mechanical PASS does not imply semantic support. Every packet warns that bounded
  literal retrieval may omit superseding/conflicting passages and requires review.
  No semantic conclusion is generated. Source instructions remain DATA.

Exit codes: 0 only for matched evidence + mechanical PASS; 1 for matched evidence
with INCOMPLETE coverage; 2 for invalid request/integrity failure/NO_MATCH. Inspect
status as well as exit code. Failures return bounded JSON; no traceback or source
text in diagnostics. Interrupted/failed calls may leave derived files, never a
successful packet. No silent reuse; choose a fresh output directory.

Acceptance: RED before code, then independent CLI tests for ordinary literal hits,
UTF-8/CRLF exact offsets, false/empty/unknown query, source conflict, actual PDF
physical pages and >32-page cap, unsupported/symlink/FIFO/depth/byte/output/time caps,
path traversal, existing output preservation, source mutation, pinned dependency
mismatch, bounded packet/hit count, and fresh worktree reproduction. Real Poppler
must run without skipped tests; fake/instrumented boundaries are identified.
