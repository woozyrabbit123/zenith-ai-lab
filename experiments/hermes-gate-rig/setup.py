"""Fetch a pinned MIT upstream and install only into this experiment's .runtime."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent
SHA = '8f817911723e3ec13e7f47fc022fdcc9e2149354'


def run(*args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


def main():
    started = time.monotonic()
    repo = ROOT.parents[1]
    origin = run('git', '-C', str(repo), 'remote', 'get-url', 'origin')
    if origin.rstrip('/').removesuffix('.git') != 'https://github.com/woozyrabbit123/zenith-ai-lab':
        raise SystemExit('Wrong lab origin; setup refused')
    runtime = ROOT / '.runtime'
    runtime.mkdir(exist_ok=True)
    env = dict(os.environ, UV_CACHE_DIR=str(runtime / 'uv-cache'),
               UV_PYTHON_INSTALL_DIR=str(runtime / 'python'),
               UV_PROJECT_ENVIRONMENT=str(runtime / 'venv'))
    upstream = runtime / 'upstream'
    if not upstream.exists():
        subprocess.run(['git', 'init', '-q', str(upstream)], check=True)
        subprocess.run(['git', '-C', str(upstream), 'remote', 'add', 'origin',
                        'https://github.com/NousResearch/hermes-agent.git'], check=True)
        subprocess.run(['git', '-C', str(upstream), 'fetch', '--depth=1', 'origin', SHA], check=True)
        subprocess.run(['git', '-C', str(upstream), 'checkout', '--detach', SHA], check=True)
    if run('git', '-C', str(upstream), 'rev-parse', 'HEAD') != SHA:
        raise SystemExit('Upstream revision mismatch')
    if run('git', '-C', str(upstream), 'status', '--porcelain', '--untracked-files=no'):
        raise SystemExit('Tracked upstream modifications refused')
    subprocess.run(['uv', 'python', 'install', '--no-bin', '3.14.8'], env=env, check=True)
    python = run('uv', 'python', 'find', '3.14.8', env=env)
    subprocess.run(['uv', 'sync', '--project', str(upstream), '--python', python,
                    '--locked', '--no-dev', '--no-default-groups'], env=env, check=True)
    receipt = {
        'upstream': SHA, 'license': 'MIT (upstream, not a licence for this lab)',
        'uv_lock_sha256': hashlib.sha256((upstream / 'uv.lock').read_bytes()).hexdigest(),
        'python': run(str(runtime / 'venv/bin/python'), '--version'),
        'uv': run('uv', '--version'), 'setup_seconds': round(time.monotonic() - started, 3),
    }
    (runtime / 'setup.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
