#!/usr/bin/env python3
"""One local invocation: pinned LENS snapshot, bounded literal hits, verification."""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import sys
from types import SimpleNamespace

LENS_COMMIT = '73239b3afb6838fc057da1e3904c5b3b4df9536b'
LENS_SHA256 = 'a1c7e02ada1224a09327eaeee3b5d7d5c7f9e4b969f645ddc33725c49167d814'
PACKET_CAP = 8192
RESERVE = 65536
EXCERPT_CAP = 384
HIT_CAP = 8


class Fault(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message


class Timeout(BaseException):
    pass


def timed_out(_signum, _frame):
    raise Timeout()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True) + '\n').encode('utf-8')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_lens():
    path = Path(__file__).resolve().parent.parent / 'sentinel-lens-0' / 'lens.py'
    if not path.is_file() or sha(path.read_bytes()) != LENS_SHA256:
        raise Fault('DEPENDENCY_MISMATCH', 'Expected the exact pinned LENS-0 implementation; nothing executed.')
    spec = importlib.util.spec_from_file_location('onecall_pinned_lens', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def shorten(text, limit=160):
    raw = text.encode('utf-8')
    return raw[:limit].decode('utf-8', 'ignore'), len(raw) > limit


def excerpt(data, position):
    start = max(0, position - 80)
    end = min(len(data), start + EXCERPT_CAP)
    while start < len(data) and data[start] & 0xc0 == 0x80:
        start += 1
    while end < len(data) and data[end] & 0xc0 == 0x80:
        end -= 1
    return start, end


def fit(packet):
    """Drop details, never coverage/integrity warnings, to enforce wire bytes."""
    while len(encode(packet)) >= PACKET_CAP and packet['gaps']:
        packet['gaps'].pop()
        packet['gap_details_omitted'] = True
    while len(encode(packet)) >= PACKET_CAP and len(packet['citations']) > 1:
        packet['citations'].pop()
        packet['retrieval']['omitted_hits'] = True
    if len(encode(packet)) >= PACKET_CAP:
        raise Fault('PACKET_LIMIT', 'No packet can be emitted within the byte limit.')


def evidence(args, lens):
    needle = args.query.encode('utf-8')
    if not args.query.strip() or not 1 <= len(needle) <= 256:
        raise Fault('INVALID_QUERY', 'Use a non-whitespace literal query of 1..256 UTF-8 bytes.')
    for value in (args.root, args.out):
        if '..' in Path(value).parts:
            raise Fault('PATH_TRAVERSAL', 'Parent traversal is refused before path normalisation.')
    if os.path.lexists(args.out):
        raise Fault('OUTPUT_EXISTS', 'Output already exists; choose a new derived directory. Nothing overwritten.')
    limits = {key: getattr(args, key) for key in lens.LIMITS}
    for key, value in limits.items():
        if not math.isfinite(value) or not 0 < value <= lens.LIMITS[key]:
            raise Fault('INVALID_LIMIT', 'Limits may only lower the frozen LENS ceilings.')
    if limits['output_bytes'] <= RESERVE:
        raise Fault('OUTPUT_LIMIT', 'Output allowance must exceed the 64 KiB wrapper reserve.')
    # The original snapshot owns source traversal, extraction, all caps and hashes.
    snapshot_limits = dict(limits, output_bytes=limits['output_bytes'] - RESERVE)
    summary, _ = lens.snapshot(SimpleNamespace(root=args.root, out=args.out, **snapshot_limits))
    manifest_path = Path(args.out) / 'manifest.json'
    bound = SimpleNamespace(manifest=str(manifest_path), manifest_sha256=summary['manifest_sha256'])
    manifest, _ = lens.load_manifest(bound)
    hits = []
    matched_chunks = 0
    extra_occurrences = False
    # At most one excerpt per physical page/text chunk; retain only the first eight.
    for source in manifest['sources']:
        for chunk in source['chunks']:
            data = lens.chunk_data(bound, chunk)
            position = data.find(needle)
            if position < 0:
                continue
            matched_chunks += 1
            extra_occurrences |= data.find(needle, position + len(needle)) >= 0
            if len(hits) == HIT_CAP:
                continue
            start, end = excerpt(data, position)
            text = lens.span(data, start, end)
            path, shortened = shorten(source['path'])
            hits.append(dict(source_id=source['id'], path=path, path_shortened=shortened,
                             source_sha256=source['sha256'], extraction_sha256=chunk['sha256'],
                             chunk=chunk['id'], page=chunk['page'], start=start, end=end, quote=text))
    gaps = []
    for gap in manifest['gaps'][:3]:
        path, short_path = shorten(gap['path'])
        reason, short_reason = shorten(gap['reason'])
        gaps.append(dict(path=path, reason=reason, detail_shortened=short_path or short_reason))
    source_set = [dict(id=s['id'], path=s['path'], sha256=s['sha256']) for s in manifest['sources']]
    packet = dict(status='MATCHES' if hits else 'NO_MATCH', query=args.query,
                  citations=hits, coverage=manifest['coverage'], mechanical='PENDING',
                  semantic='REVIEW_REQUIRED',
                  root_hashes=dict(manifest_sha256=summary['manifest_sha256'],
                                   observed_sources_sha256=sha(encode(source_set)), lens_sha256=LENS_SHA256),
                  gap_count=len(manifest['gaps']), gaps=gaps,
                  gap_details_omitted=len(gaps) < len(manifest['gaps']),
                  retrieval=dict(order='path/page, first literal occurrence per chunk',
                                 matched_chunks=matched_chunks, omitted_hits=matched_chunks > len(hits) or extra_occurrences),
                  warnings=['Literal retrieval may omit superseding or conflicting passages; review full sources.',
                            'Mechanical verification checks bytes and coverage, not semantic support.'],
                  artifacts=dict(manifest='manifest.json', citations='citations.json'))
    if not hits:
        packet['answer'] = 'UNKNOWN'
    fit(packet)
    fd = lens.directory(args.out)
    written = sum(p.stat(follow_symlinks=False).st_size for p in Path(args.out).iterdir())

    def write(name, raw):
        nonlocal written
        if written + len(raw) > limits['output_bytes']:
            raise Fault('OUTPUT_LIMIT', 'Combined derived output exceeded its allowance.')
        f = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        with os.fdopen(f, 'wb') as stream:
            stream.write(raw)
        written += len(raw)

    try:
        # Extra packet fields are harmless to the original exact-span verifier.
        citation_path = Path(args.out) / 'citations.json'
        write('citations.json', encode(packet['citations']))
        verification, _ = lens.verify(SimpleNamespace(**vars(bound), root=args.root, citations=str(citation_path)))
        packet['mechanical'] = verification['mechanical']
        if hits and verification['mechanical'] == 'FAIL':
            packet['status'] = 'INTEGRITY_FAILURE'
        packet['verification_errors'] = [shorten(error)[0] for error in verification['errors'][:2]]
        packet['verification_errors_omitted'] = len(verification['errors']) > 2
        # Snapshot gaps already live in the manifest. Newly observed verifier gaps
        # also prevent a complete current-scope claim, even if citations are valid.
        if verification['gaps']:
            packet['coverage'] = 'INCOMPLETE'
        if not hits:
            packet['warnings'].append('NO_CITATIONS: LENS rejects an empty citation list; no evidence answer is available.')
        fit(packet)
        # Fitting after errors may omit a citation already verified. Persist the
        # verified superset as citations.json; packet citations are a valid subset.
        raw = encode(packet)
        write('packet.json', raw)
    finally:
        os.close(fd)
    code = 0 if hits and packet['mechanical'] == 'PASS' else 1 if hits and packet['mechanical'] == 'INCOMPLETE' else 2
    return packet, code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    command = sub.add_parser('evidence')
    command.add_argument('--root', required=True)
    command.add_argument('--query', required=True)
    command.add_argument('--out', required=True)
    # Limits are parsed here but ceilings come exclusively from the pinned engine.
    for name in ('files', 'entries', 'depth', 'file_bytes', 'total_bytes', 'output_bytes', 'pages'):
        command.add_argument('--' + name.replace('_', '-'), type=int)
    command.add_argument('--seconds', type=float)
    args = parser.parse_args(argv)
    lens = None
    try:
        lens = load_lens()
        for key, default in lens.LIMITS.items():
            if getattr(args, key) is None:
                setattr(args, key, default)
        # Deadline spans snapshot + retrieval + original verifier + output writes.
        if not math.isfinite(args.seconds) or not 0 < args.seconds <= lens.LIMITS['seconds']:
            raise Fault('INVALID_LIMIT', 'Seconds must be positive and at most the LENS ceiling.')
        signal.signal(signal.SIGALRM, timed_out)
        signal.setitimer(signal.ITIMER_REAL, args.seconds)
        packet, code = evidence(args, lens)
    except Fault as exc:
        packet, code = dict(status='ERROR', coverage='INCOMPLETE', mechanical='FAIL',
                            semantic='REVIEW_REQUIRED', error=dict(code=exc.code, message=exc.message)), 2
    except Timeout:
        packet, code = dict(status='ERROR', coverage='INCOMPLETE', mechanical='FAIL', semantic='REVIEW_REQUIRED',
                            error=dict(code='TIME_LIMIT', message='Whole onecall operation reached its time limit.')), 2
    except OSError as exc:
        packet, code = dict(status='ERROR', coverage='INCOMPLETE', mechanical='FAIL', semantic='REVIEW_REQUIRED',
                            error=dict(code='OUTPUT_EXISTS' if exc.errno == 17 else 'PATH_REFUSED', os_errno=exc.errno,
                                       message='Source/output path was unavailable or refused. Choose a fresh, separate output directory.')), 2
    except Exception:
        # Keep source text, paths, extraction stderr and exception repr out of diagnostics.
        packet, code = dict(status='ERROR', coverage='INCOMPLETE', mechanical='FAIL', semantic='REVIEW_REQUIRED',
                            error=dict(code='OPERATION_FAILED', message='Operation refused or failed; no successful evidence packet.')) , 2
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    sys.stdout.buffer.write(encode(packet))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
