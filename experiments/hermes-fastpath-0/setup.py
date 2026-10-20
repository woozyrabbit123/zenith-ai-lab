"""Task-local pinned upstream, interpreter and dependency setup."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent
SHA = '8f817911723e3ec13e7f47fc022fdcc9e2149354'


def output(*args):
    return subprocess.check_output(args, text=True).strip()


def main():
    start = time.monotonic()
    origin = output('git', '-C', str(ROOT.parents[1]), 'remote', 'get-url', 'origin')
    if origin.removesuffix('.git') != 'https://github.com/woozyrabbit123/zenith-ai-lab':
        raise SystemExit('Unexpected lab origin')
    runtime = ROOT / '.runtime'
    runtime.mkdir(exist_ok=True)
    upstream = runtime / 'upstream'
    if not upstream.exists():
        subprocess.run(['git', 'init', '-q', str(upstream)], check=True)
        subprocess.run(['git', '-C', str(upstream), 'remote', 'add', 'origin',
                        'https://github.com/NousResearch/hermes-agent.git'], check=True)
        subprocess.run(['git', '-C', str(upstream), 'fetch', '--depth=1', 'origin', SHA], check=True)
        subprocess.run(['git', '-C', str(upstream), 'checkout', '--detach', SHA], check=True)
    if output('git', '-C', str(upstream), 'rev-parse', 'HEAD') != SHA:
        raise SystemExit('Upstream SHA mismatch')
    if output('git', '-C', str(upstream), 'status', '--porcelain', '--untracked-files=no'):
        raise SystemExit('Tracked upstream source modifications refused')
    env = dict(os.environ, UV_CACHE_DIR=str(runtime / 'uv-cache'),
               UV_PYTHON_INSTALL_DIR=str(runtime / 'python'),
               UV_PROJECT_ENVIRONMENT=str(runtime / 'venv'))
    subprocess.run(['uv', 'python', 'install', '--no-bin', '3.14.8'], env=env, check=True)
    python = subprocess.check_output(['uv', 'python', 'find', '3.14.8'], env=env, text=True).strip()
    subprocess.run(['uv', 'sync', '--project', str(upstream), '--python', python,
                    '--locked', '--no-dev', '--no-default-groups'], env=env, check=True)
    result = {'upstream': SHA, 'python': output(str(runtime / 'venv/bin/python'), '--version'),
              'uv': output('uv', '--version'), 'setup_seconds': round(time.monotonic()-start, 3),
              'lock_sha256': hashlib.sha256((upstream/'uv.lock').read_bytes()).hexdigest()}
    (runtime/'setup.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
