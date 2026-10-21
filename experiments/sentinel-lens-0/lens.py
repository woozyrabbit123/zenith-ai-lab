#!/usr/bin/env python3
"""Bounded local extraction and mechanical citation checks. Source text is DATA."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import resource
import signal
import shutil
import stat
import subprocess
import tempfile
import time

LIMITS = dict(files=128, entries=512, depth=8, file_bytes=4 << 20,
              total_bytes=16 << 20, output_bytes=16 << 20, pages=32, seconds=30.0)
MANIFEST_CAP = 4 << 20
CITATION_CAP = 1 << 20
QUOTE_CAP = 64 << 10
NOFOLLOW = os.O_NOFOLLOW


class Invalid(Exception):
    pass


class Deadline(BaseException):
    """Not swallowed by per-source GAP handling."""


def deadline_expired(_signum, _frame):
    raise Deadline()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode()


def relative(path):
    p = Path(path)
    if p.is_absolute() or not p.parts or any(x in ('..', '.') for x in p.parts):
        raise Invalid('path escape or invalid relative path')
    return p.parts


def directory(path):
    """Walk absolute ancestors by descriptor; never follow directory symlinks."""
    path = Path(os.path.abspath(path))
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_at(root, rel, cap):
    parts = relative(rel)
    fd = directory(root)
    try:
        for part in parts[:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        f = os.open(parts[-1], os.O_RDONLY | NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            before = os.fstat(f)
            if not stat.S_ISREG(before.st_mode):
                raise Invalid('not a regular file')
            if before.st_size > cap:
                raise Invalid('file byte cap')
            with os.fdopen(f, 'rb', closefd=False) as stream:
                data = stream.read(cap + 1)
            after = os.fstat(f)
            if len(data) > cap:
                raise Invalid('file byte cap')
            if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                    after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise Invalid('source changed while reading')
            return data
        finally:
            os.close(f)
    finally:
        os.close(fd)


def read_file(path, cap):
    p = Path(os.path.abspath(path))
    return read_at(p.parent, p.name, cap)


class Budget:
    def __init__(self, limits):
        self.limits = limits
        self.deadline = time.monotonic() + limits['seconds']

    def remaining(self):
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise Invalid('time cap')
        return left


def inventory(root, limits, budget):
    """Finite directory traversal; record every inspected entry, including gaps."""
    records, gaps = [], []
    stopped = False
    observed = 0

    def walk(fd, prefix, level):
        nonlocal stopped, observed
        budget.remaining()
        # Do not materialise an unbounded directory before applying the entry cap.
        items = []
        with os.scandir(fd) as entries:
            for item in entries:
                budget.remaining()
                if observed >= limits['entries']:
                    gaps.append(dict(path=prefix or '.', reason='entry cap'))
                    stopped = True
                    break
                observed += 1
                items.append((item.name, item.stat(follow_symlinks=False).st_mode))
        for name, mode in sorted(items):
            budget.remaining()
            path = f'{prefix}/{name}' if prefix else name
            kind = 'directory' if stat.S_ISDIR(mode) else 'file' if stat.S_ISREG(mode) else 'symlink' if stat.S_ISLNK(mode) else 'special'
            records.append(dict(path=path, kind=kind))
            if kind == 'directory':
                if level >= limits['depth']:
                    gaps.append(dict(path=path, reason='depth cap'))
                elif not stopped:
                    try:
                        child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW, dir_fd=fd)
                        try:
                            walk(child, path, level + 1)
                        finally:
                            os.close(child)
                    except (OSError, Invalid) as exc:
                        gaps.append(dict(path=path, reason=reason(exc)))
            elif kind != 'file':
                gaps.append(dict(path=path, reason='symlink/path escape' if kind == 'symlink' else 'not regular'))

    fd = directory(root)
    try:
        walk(fd, '', 1)
    except (OSError, Invalid) as exc:
        gaps.append(dict(path='.', reason=reason(exc)))
    finally:
        os.close(fd)
    return sorted(records, key=lambda x: x['path']), gaps


def reason(exc):
    # No tool stderr or source text in diagnostics.
    return str(exc) if isinstance(exc, Invalid) else f'OS error {exc.errno}'


def process(args, budget, cap, combined=False):
    """Bound stdout/stderr on disk AND execution time; never invoke a shell."""
    def bound_child():
        resource.setrlimit(resource.RLIMIT_FSIZE, (cap, cap))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            p = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=out, stderr=out if combined else err,
                               timeout=budget.remaining(), preexec_fn=bound_child, check=False)
        except subprocess.TimeoutExpired as exc:
            raise Invalid('time cap in extractor') from exc
        if p.returncode:
            raise Invalid('extractor failed or output cap')
        out.seek(0)
        data = out.read(cap + 1)
        if len(data) >= cap:
            raise Invalid('extractor output cap')
        budget.remaining()
        return data


def executable(name, budget):
    path = shutil.which(name)
    if not path:
        raise Invalid(f'{name} unavailable')
    # Installed executable may itself be a symlink; resolve only executable location.
    path = str(Path(path).resolve(strict=True))
    sha = digest(read_file(path, 32 << 20))
    version = process([path, '-v'], budget, 16384, combined=True)
    return dict(path=path, sha256=sha, version=version.decode('utf-8', 'strict').splitlines()[0])


def output_directory(root, out):
    root, out = Path(os.path.abspath(root)), Path(os.path.abspath(out))
    if root == out or root in out.parents or out in root.parents:
        raise Invalid('output overlaps input root')
    root_fd = directory(root)
    os.close(root_fd)
    parent = directory(out.parent)
    try:
        os.mkdir(out.name, mode=0o700, dir_fd=parent)
        fd = os.open(out.name, os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW, dir_fd=parent)
    finally:
        os.close(parent)
    return root, out, fd


def snapshot(args):
    limits = {k: getattr(args, k) for k in LIMITS}
    for key, value in limits.items():
        if not math.isfinite(value) or value <= 0 or value > LIMITS[key]:
            raise Invalid('limits must be positive and no greater than frozen ceilings')
    budget = Budget(limits)
    root, out, out_fd = output_directory(args.root, args.out)
    manifest = dict(format='lens-0-v1', limits=limits, inventory=[], sources=[], gaps=[])
    spent = 0

    def write(name, data):
        nonlocal spent
        if len(data) + spent > limits['output_bytes']:
            raise Invalid('derived output byte cap')
        f = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | NOFOLLOW, 0o600, dir_fd=out_fd)
        with os.fdopen(f, 'wb') as stream:
            stream.write(data)
        spent += len(data)

    try:
        manifest['inventory'], manifest['gaps'] = inventory(root, limits, budget)
        total = 0
        tools = None
        attempted = 0
        for item in manifest['inventory']:
            if item['kind'] != 'file':
                continue
            path = item['path']
            source = None
            try:
                budget.remaining()
                attempted += 1
                if attempted > limits['files']:
                    raise Invalid('file count cap')
                data = read_at(root, path, min(limits['file_bytes'], limits['total_bytes'] - total))
                total += len(data)
                sid = digest(path.encode('utf-8'))
                source = dict(id=sid, path=path, sha256=digest(data), bytes=len(data), chunks=[])
                manifest['sources'].append(source)
                suffix = Path(path).suffix.lower()
                def retain(page, text, extractor):
                    budget.remaining()
                    cid = sid + (f':page:{page}' if page else ':text')
                    name = f'{sid}.{page or 0}.utf8'
                    write(name, text)
                    source['chunks'].append(dict(id=cid, page=page, file=name, sha256=digest(text), bytes=len(text), extractor=extractor))
                if suffix in ('.txt', '.md'):
                    data.decode('utf-8', 'strict')
                    retain(None, data, dict(name='identity-utf8', options=[], version='1', sha256=digest(b'identity-utf8-v1')))
                elif suffix == '.pdf':
                    if tools is None:
                        tools = {name: executable(name, budget) for name in ('pdfinfo', 'pdftotext')}
                    # Frozen copy avoids Poppler reopening a source path after its hash read.
                    with tempfile.TemporaryDirectory(prefix='lens-pdf-') as temp:
                        pdf = Path(temp) / 'input.pdf'
                        pdf.write_bytes(data)
                        info = process([tools['pdfinfo']['path'], str(pdf)], budget, 65536).decode('utf-8', 'replace')
                        if not re.search(r'^Encrypted:\s+no\s*$', info, re.M):
                            raise Invalid('encrypted or unknown PDF encryption')
                        pages_match = re.search(r'^Pages:\s+(\d+)\s*$', info, re.M)
                        if not pages_match:
                            raise Invalid('unknown PDF page count')
                        pages = int(pages_match[1])
                        if pages < 1:
                            raise Invalid('empty PDF')
                        source['pdfinfo'] = tools['pdfinfo']
                        if pages > limits['pages']:
                            manifest['gaps'].append(dict(path=path, reason='PDF page cap'))
                        for page in range(1, min(pages, limits['pages']) + 1):
                            options = ['-f', str(page), '-l', str(page), '-enc', 'UTF-8', '-layout']
                            text = process([tools['pdftotext']['path'], *options, str(pdf), '-'], budget,
                                           min(limits['file_bytes'], limits['output_bytes'] - spent))
                            text.decode('utf-8', 'strict')
                            if not text.strip():
                                raise Invalid('empty/scanned PDF page; OCR unavailable')
                            retain(page, text, dict(name='pdftotext', **tools['pdftotext'], options=options))
                else:
                    raise Invalid('unsupported source type')
                # Detect edits made during extraction, including same-length changes.
                if digest(read_at(root, path, limits['file_bytes'])) != source['sha256']:
                    raise Invalid('source changed during snapshot')
            except (OSError, ValueError, Invalid, subprocess.TimeoutExpired) as exc:
                manifest['gaps'].append(dict(path=path, reason=reason(exc) if isinstance(exc, (OSError, Invalid)) else 'invalid UTF-8 or extractor timeout'))
        if not manifest['sources']:
            manifest['gaps'].append(dict(path='.', reason='no readable sources'))
        final_inventory, final_gaps = inventory(root, limits, budget)
        if final_inventory != manifest['inventory']:
            manifest['gaps'].append(dict(path='.', reason='inventory changed during snapshot'))
        # Final traversal gaps remain gaps, even when the set of observed entries matches.
        for gap in final_gaps:
            if gap not in manifest['gaps']:
                manifest['gaps'].append(gap)
        manifest['coverage'] = 'INCOMPLETE' if manifest['gaps'] else 'COMPLETE'
        raw = encoded(manifest)
        if len(raw) > MANIFEST_CAP:
            raise Invalid('manifest byte cap')
        write('manifest.json', raw)
        return dict(coverage=manifest['coverage'], manifest_sha256=digest(raw),
                    sources=len(manifest['sources']), gaps=manifest['gaps'], derived_bytes=spent), 1 if manifest['gaps'] else 0
    finally:
        os.close(out_fd)


def load_manifest(args):
    raw = read_file(args.manifest, MANIFEST_CAP)
    if digest(raw) != args.manifest_sha256:
        raise Invalid('manifest hash mismatch')
    m = json.loads(raw)
    if m['format'] != 'lens-0-v1':
        raise Invalid('unknown manifest format')
    for k, ceiling in LIMITS.items():
        v = m['limits'][k]
        if not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 < v <= ceiling:
            raise Invalid('invalid manifest limits')
    if len(m['sources']) > LIMITS['files'] or len(m['inventory']) > LIMITS['entries']:
        raise Invalid('manifest count cap')
    chunks = {}
    for s in m['sources']:
        relative(s['path'])
        if s['id'] != digest(s['path'].encode('utf-8')):
            raise Invalid('source id mismatch')
        if len(s['chunks']) > LIMITS['pages']:
            raise Invalid('chunk count cap')
        for c in s['chunks']:
            if len(relative(c['file'])) != 1 or c['id'] in chunks:
                raise Invalid('invalid chunk path or duplicate id')
            chunks[c['id']] = c
    return m, chunks


def chunk_data(args, chunk):
    data = read_at(Path(os.path.abspath(args.manifest)).parent, chunk['file'], LIMITS['file_bytes'])
    if digest(data) != chunk['sha256'] or len(data) != chunk['bytes']:
        raise Invalid('extraction hash/length mismatch')
    data.decode('utf-8', 'strict')
    return data


def span(data, start, end):
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(data) or end - start > QUOTE_CAP:
        raise Invalid('invalid/oversized byte range')
    # Both ends must be UTF-8 codepoint boundaries, not merely a decodable middle.
    data[:start].decode('utf-8', 'strict')
    data[end:].decode('utf-8', 'strict')
    return data[start:end].decode('utf-8', 'strict')


def quote(args):
    _, chunks = load_manifest(args)
    if args.chunk not in chunks:
        raise Invalid('unknown chunk')
    c = chunks[args.chunk]
    data = chunk_data(args, c)
    return dict(chunk=args.chunk, start=args.start, end=args.end, quote=span(data, args.start, args.end),
                extraction_sha256=c['sha256']), 0


def verify(args):
    errors, gaps = [], []
    try:
        m, chunks = load_manifest(args)
        budget = Budget(m['limits'])
        records, now_gaps = inventory(args.root, m['limits'], budget)
        gaps = m['gaps'] + now_gaps
        if records != m['inventory']:
            errors.append('source inventory changed')
        total = 0
        extracted_total = 0
        checked_tools = {}
        for source in m['sources']:
            budget.remaining()
            try:
                data = read_at(args.root, source['path'], m['limits']['file_bytes'])
                total += len(data)
                if total > m['limits']['total_bytes']:
                    raise Invalid('total input byte cap')
                if digest(data) != source['sha256'] or len(data) != source['bytes']:
                    raise Invalid('source hash/length mismatch')
                for c in source['chunks']:
                    budget.remaining()
                    extracted_total += len(chunk_data(args, c))
                    if extracted_total > m['limits']['output_bytes']:
                        raise Invalid('extracted byte cap')
                extractors = [c['extractor'] for c in source['chunks']]
                if 'pdfinfo' in source:
                    extractors.append(source['pdfinfo'])
                for ex in extractors:
                    budget.remaining()
                    if 'path' in ex:
                        if ex['path'] not in checked_tools:
                            checked_tools[ex['path']] = digest(read_file(ex['path'], 32 << 20))
                        if checked_tools[ex['path']] != ex['sha256']:
                            raise Invalid('extractor executable hash mismatch')
            except (OSError, Invalid, ValueError) as exc:
                errors.append(source['path'] + ': ' + (reason(exc) if isinstance(exc, (OSError, Invalid)) else 'invalid data'))
        citations = json.loads(read_file(args.citations, CITATION_CAP))
        if not isinstance(citations, list) or not 1 <= len(citations) <= 128:
            raise Invalid('expected 1..128 citations')
        for i, q in enumerate(citations):
            budget.remaining()
            try:
                c = chunks[q['chunk']]
                expected = span(chunk_data(args, c), q['start'], q['end'])
                if expected != q['quote'] or q.get('extraction_sha256') != c['sha256']:
                    raise Invalid('quote/extraction hash mismatch')
            except (KeyError, TypeError, OSError, Invalid, ValueError) as exc:
                errors.append(f'citation {i}: invalid span, quote, extraction or chunk')
        if not m['sources'] or m['coverage'] != 'COMPLETE':
            gaps.append(dict(path='.', reason='snapshot coverage incomplete'))
    except (OSError, Invalid, ValueError, KeyError, TypeError) as exc:
        errors.append(reason(exc) if isinstance(exc, (OSError, Invalid)) else 'invalid artifact schema/data')
    mechanical = 'FAIL' if errors else 'INCOMPLETE' if gaps else 'PASS'
    return dict(mechanical=mechanical, semantic='REVIEW_REQUIRED', errors=errors, gaps=gaps), {'PASS': 0, 'INCOMPLETE': 1, 'FAIL': 2}[mechanical]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    snap = sub.add_parser('snapshot')
    snap.add_argument('--root', required=True)
    snap.add_argument('--out', required=True)
    for key, default in LIMITS.items():
        snap.add_argument('--' + key.replace('_', '-'), type=float if key == 'seconds' else int, default=default)
    for name in ('quote', 'verify'):
        p = sub.add_parser(name)
        p.add_argument('--manifest', required=True)
        p.add_argument('--manifest-sha256', required=True)
        if name == 'quote':
            p.add_argument('--chunk', required=True)
            p.add_argument('--start', type=int, required=True)
            p.add_argument('--end', type=int, required=True)
        else:
            p.add_argument('--root', required=True)
            p.add_argument('--citations', required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGALRM, deadline_expired)
    signal.setitimer(signal.ITIMER_REAL, LIMITS['seconds'])
    try:
        result, code = {'snapshot': snapshot, 'quote': quote, 'verify': verify}[args.command](args)
    except Deadline:
        result, code = dict(error='whole-operation time cap', coverage='INCOMPLETE'), 2
    except (OSError, Invalid, ValueError, KeyError, TypeError, subprocess.TimeoutExpired, IndexError, RecursionError) as exc:
        result, code = dict(error=reason(exc) if isinstance(exc, (OSError, Invalid)) else 'invalid data or extractor timeout', coverage='INCOMPLETE'), 2
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    print(encoded(result).decode(), end='')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
