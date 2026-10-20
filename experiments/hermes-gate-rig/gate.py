"""Experimental terminal tripwire. No arbitrary-shell security guarantee."""
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
from urllib.parse import urlsplit


def canonical_origin(value):
    """Deliberately accept only github.com HTTPS and git SSH forms."""
    if value.startswith('git@github.com:'):
        path = value[len('git@github.com:'):]
    else:
        parsed = urlsplit(value)
        if parsed.scheme not in ('https', 'ssh') or parsed.hostname != 'github.com':
            raise ValueError('unsupported origin')
        if parsed.port is not None or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('ambiguous origin')
        if (parsed.scheme == 'https' and parsed.username) or (parsed.scheme == 'ssh' and parsed.username != 'git'):
            raise ValueError('unexpected user')
        path = parsed.path.removeprefix('/')
    if path.endswith('.git'):
        path = path[:-4]
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', path):
        raise ValueError('invalid repository path')
    return path.casefold()


def identity(expected):
    try:
        # Raw URLs, not git's insteadOf expansion. Both fetch and push forms are checked.
        result = subprocess.run(['git', 'config', '--get-all', 'remote.origin.url'],
                                capture_output=True, text=True, check=False)
        urls = result.stdout.splitlines()
        push = subprocess.run(['git', 'config', '--get-all', 'remote.origin.pushurl'],
                              capture_output=True, text=True, check=False).stdout.splitlines()
        if result.returncode or len(urls) != 1 or len(push) > 1:
            raise ValueError('missing or multiple origin URLs')
        if canonical_origin(urls[0]) != expected or any(canonical_origin(u) != expected for u in push):
            raise ValueError('wrong origin')
        # Explicitly require the current directory to belong to a worktree.
        subprocess.run(['git', 'rev-parse', '--show-toplevel'], check=True, capture_output=True)
        return 0
    except (ValueError, subprocess.CalledProcessError) as exc:
        print('IDENTITY-GUARD: refused: ' + str(exc), file=sys.stderr)
        return 97


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--expected', default='fixture/allowed')
    parser.add_argument('--mode', default='prefix')
    parser.add_argument('--audit', type=Path)
    args = parser.parse_args()
    if args.check:
        return identity(args.expected)
    payload = json.load(sys.stdin)
    with args.audit.open('a') as out:
        out.write(json.dumps({'mode': args.mode, 'cwd': payload.get('cwd'),
                              'tool': payload.get('tool_name'), 'args': payload.get('tool_input')}) + '\n')
    if args.mode == 'crash':
        raise RuntimeError('synthetic hook crash')
    if args.mode == 'timeout':
        time.sleep(3)
        return 0
    if args.mode == 'empty':
        return 0
    if args.mode == 'object':
        print('{}')
        return 0
    if args.mode == 'malformed':
        print('not-json')
        return 0
    if args.mode == 'veto':
        print(json.dumps({'action': 'block', 'message': 'synthetic terminal veto'}))
        return 0
    command = payload['tool_input']['command']
    if args.mode == 'override':
        replacement = "printf 'synthetic-output\\n' >> out.txt"
    else:
        check = shlex.join([sys.executable, str(Path(__file__).resolve()), '--check', '--expected', args.expected])
        replacement = check + ' || exit 97; ' + command
    print(json.dumps({'action': 'modify', 'args': {'command': replacement}}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
