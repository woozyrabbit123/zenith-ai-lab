"""Bounded inspect/update/verify command used identically in both execution paths."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import stat
import tempfile


class Refused(Exception):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def atomic_write(path, data):
    """Fsync the file and rename directory; no OS-crash guarantee is inferred."""
    descriptor, temp = tempfile.mkstemp(prefix='.operation-', dir=path.parent)
    try:
        if path.exists():
            os.fchmod(descriptor, stat.S_IMODE(path.stat().st_mode))
        with os.fdopen(descriptor, 'wb') as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def scope(request):
    root = Path(request['root'])
    if not root.is_absolute() or root.resolve() != root or Path.cwd().resolve() != root:
        raise Refused('working directory does not match approved root')
    origin = subprocess.run(['git', 'config', '--get-all', 'remote.origin.url'],
                            capture_output=True, text=True, check=False)
    if origin.returncode or origin.stdout.splitlines() != [request['origin']]:
        raise Refused('repository origin mismatch or ambiguity')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if head != request['head']:
        raise Refused('repository HEAD mismatch')
    for name in ('settings.json', 'notes.txt', '.fastpath', '.fastpath/receipt.json', '.fastpath/lock'):
        if (root/name).is_symlink():
            raise Refused('symlink outside the approved file contract')
    if digest((root/'notes.txt').read_bytes()) != request['notes_sha256']:
        raise Refused('neighbour changed')
    return root


def step(phase, request, disconnect=False):
    root = scope(request)
    fingerprint = digest(encode(request))
    receipt_path = root/'.fastpath/receipt.json'
    target = root/'settings.json'
    # The operator provisions this lock once; invalid requests create no lock/state files.
    with (root/'.fastpath/lock').open('rb') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
        if receipt and receipt.get('request_sha256') != fingerprint:
            raise Refused('receipt belongs to another approved request')
        current = target.read_bytes()
        current_sha = digest(current)
        before, after = request['before_sha256'], request['after_sha256']
        state = receipt.get('state') if receipt else None
        base = {'operation_id': request['operation_id'], 'request_sha256': fingerprint,
                'before_sha256': before, 'after_sha256': after}
        if phase == 'inspect':
            if current_sha == before and state in (None, 'prepared'):
                return {'ok': True, 'step': phase, 'status': 'ready', 'sha256': current_sha}
            if current_sha == after and state in ('prepared', 'applied', 'verified'):
                return {'ok': True, 'step': phase, 'status': 'reconcile_or_repeat', 'sha256': current_sha}
            raise Refused('unexpected starting bytes or unowned completed state')
        if phase == 'update':
            if current_sha == after and state in ('prepared', 'applied', 'verified'):
                if state == 'prepared':
                    atomic_write(receipt_path, encode({**base, 'state': 'applied'}))
                return {'ok': True, 'step': phase, 'status': 'already_applied', 'wrote_settings': False}
            if current_sha != before or state not in (None, 'prepared'):
                raise Refused('update precondition changed')
            needle = b'"mode": "draft"'
            if current.count(needle) != 1:
                raise Refused('mode token is not unique')
            updated = current.replace(needle, b'"mode": "ready"', 1)
            parsed = json.loads(current)
            if parsed.get('mode') != 'draft' or json.loads(updated) != {**parsed, 'mode': 'ready'}:
                raise Refused('operation is not the approved one-key update')
            if digest(updated) != after:
                raise Refused('approved after hash mismatch')
            if state is None:
                atomic_write(receipt_path, encode({**base, 'state': 'prepared'}))
            atomic_write(target, updated)
            if disconnect:
                # Explicit process-fault fixture: the prepared receipt and new file already exist.
                os._exit(75)
            atomic_write(receipt_path, encode({**base, 'state': 'applied'}))
            return {'ok': True, 'step': phase, 'status': 'applied', 'wrote_settings': True}
        if current_sha != after or state not in ('applied', 'verified'):
            return {'ok': False, 'step': phase, 'status': 'verify_failed',
                    'observed_sha256': current_sha, 'expected_sha256': after}
        if state != 'verified':
            atomic_write(receipt_path, encode({**base, 'state': 'verified'}))
        return {'ok': True, 'step': phase, 'status': 'verified', 'sha256': current_sha}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=('inspect', 'update', 'verify'))
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--simulate-disconnect-after-write', action='store_true')
    args = parser.parse_args()
    try:
        result = step(args.phase, json.loads(args.request.read_text()), args.simulate_disconnect_after_write)
    except (Refused, ValueError, subprocess.CalledProcessError) as exc:
        result = {'ok': False, 'step': args.phase, 'status': 'refused', 'error': str(exc)}
    except OSError as exc:
        result = {'ok': False, 'step': args.phase,
                  'status': 'verify_failed' if args.phase == 'verify' else 'update_failed',
                  'error_type': type(exc).__name__, 'error': str(exc)}
    print(json.dumps(result, sort_keys=True))
    return 0 if result['ok'] else 20


if __name__ == '__main__':
    raise SystemExit(main())
