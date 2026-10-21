# LENS-0 frozen contract

One on-demand Python stdlib CLI, no integration/installation. Native rg/Git/Poppler
remain the search, versioning and extraction tools. The missing operation is a
retained, bounded UTF-8 extraction with citations bound to source + extraction
hashes and byte ranges, followed by one mechanical verification across the finite
inventoried scope. Kit source is unavailable; its documented literal matches are
not evidence of this operation. Native probes will accompany the result.

Commands:

- `snapshot --root ROOT --out NEW_SIBLING_DIR`: explicit input scope; output must
  not overlap it or exist. Inventory all entries within fixed ceilings; regular
  `.md`, `.txt` (strict UTF-8) and `.pdf` only. Retain text exactly, PDFs one explicit
  `-f N -l N -enc UTF-8 -layout` invocation per physical page, with Poppler version,
  executable hash and options. Empty/encrypted/invalid/unsupported/unreadable,
  symlink, depth/count/byte/time/output caps => GAP/INCOMPLETE, never completeness.
  Manifest records relative paths, deterministic path-derived IDs, source hashes,
  extraction hashes, finite inventory, limits and coverage. Original bytes untouched.
- `quote --manifest M --manifest-sha256 HASH --chunk ID --start B --end E`:
  emits one citation with exact UTF-8 text at zero-based half-open byte range.
  Invalid UTF-8 boundary, invalid range or changed snapshot is an error.
- `verify --manifest M --manifest-sha256 HASH --root ROOT --citations JSON`:
  verifies the externally retained manifest digest, all extraction hashes, current
  source hashes, inventoried scope (including additions/deletions), tool hash,
  and each citation's exact bytes/range. PASS requires finite complete coverage
  and no errors. INCOMPLETE retains valid mechanical checks but has coverage gaps;
  FAIL means integrity/citation error. Semantic status always REVIEW_REQUIRED.
  Empty citations never pass. Superseding passages are a semantic review obligation,
  not an automatic contradiction detector. Tampering with both artifact and expected
  digest is outside trust; this is not an adversarial sandbox or authenticity proof.

Defaults/ceilings: 128 files, 512 directory entries, depth 8, 4 MiB/file,
16 MiB total input, 16 MiB total derived output, 32 pages/PDF, 30 s whole operation;
user settings may only lower these. 128 citations, 64 KiB/quote, 1 MiB citation JSON;
4 MiB manifest. Bounded subprocesses, no shell, no source text executed, no network.
Linux regular-file no-follow descriptor reads; no packages or downloads. Sources
must be quiescent while snapshotting; source changes are checked again at verify.

Acceptance: independent subprocess tests for ordinary and PDF spans; original byte
preservation; source mutation; bogus quote; wrong span; multibyte/CRLF; symlink/path
escape/output overlap; all cap categories; invalid/empty PDF; retained-text/manifest
mutation; added/deleted inputs; hostile source text as data; mechanical PASS with a
superseded claim separately marked CONTRADICTED in a useful synthetic brief. Missing
Poppler is INCOMPLETE; Poppler tests must actually run in the reported cloud suite.
Test-first RED is recorded before implementation; GREEN must run the same suite.
