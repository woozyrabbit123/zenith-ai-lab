"""Run finite real-Hermes fixtures, then independently inspect filesystem effects."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
import time

from stub import ScriptedModel
from verify import check, contract, effects, CONTRACT_SHA256

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / '.runtime'
PYTHON = RUNTIME / 'venv/bin/python'
UPSTREAM = RUNTIME / 'upstream'


def source_hashes():
    paths = sorted(ROOT.glob('*.py')) + [ROOT / 'contract.json', ROOT / 'adoption.json']
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def git(directory, *args):
    return subprocess.check_output(['git', '-C', str(directory), *args], text=True,
                                   stderr=subprocess.DEVNULL).strip()


def fixture(root):
    for name, url in {
        'allowed': 'https://github.com/fixture/allowed.git',
        'wrong': 'https://github.com/fixture/wrong.git',
        'lookalike': 'https://github.com/evil-fixture/allowed.git',
        'ssh': 'git@github.com:fixture/allowed.git',
        'multiple': 'https://github.com/fixture/allowed.git', 'missing': None,
    }.items():
        path = root / name
        path.mkdir()
        git(path, 'init', '-q')
        if url:
            git(path, 'remote', 'add', 'origin', url)
    git(root / 'multiple', 'config', '--add', 'remote.origin.url', 'https://github.com/fixture/other.git')
    git(root / 'allowed', '-c', 'user.name=Synthetic Fixture', '-c', 'user.email=fixture@example.invalid',
        'commit', '-q', '--allow-empty', '-m', 'synthetic base')
    git(root / 'allowed', 'worktree', 'add', '-q', '--detach', str(root / 'linked'))


def calls_for(case, root):
    q = shlex.quote
    write = "printf 'synthetic-output\\n' >> out.txt"
    args = {'command': write, 'timeout': 5}
    if case.get('workdir'):
        args['workdir'] = str(root / case['workdir'])
    wrong = root / 'wrong/out.txt'
    action = case.get('action')
    if action == 'write_file':
        return [('write_file', {'path': str(wrong), 'content': 'synthetic-output\n'})]
    if action == 'patch':
        return [('terminal', {'command': 'true', 'timeout': 5}),
                ('read_file', {'path': str(wrong)}),
                ('patch', {'path': str(wrong), 'old_string': 'old-output\n',
                           'new_string': 'synthetic-output\n'})]
    if action == 'recovery':
        return [('terminal', args), ('terminal', {**args, 'workdir': str(root / 'allowed')})]
    if action == 'cd':
        args['command'] = 'cd ' + q(str(root / 'wrong')) + ' && ' + write
    elif action == 'python':
        code = 'from pathlib import Path; Path(' + repr(str(wrong)) + ").write_text('synthetic-output\\n')"
        args['command'] = shlex.join([str(PYTHON), '-c', code])
    elif action == 'heredoc':
        args['command'] = 'cat > ' + q(str(wrong)) + " <<'SYNTHETIC'\nsynthetic-output\nSYNTHETIC"
    elif action == 'subshell':
        args['command'] = '(cd ' + q(str(root / 'wrong')) + ' && ' + write + ')'
    elif action == 'absolute':
        args['command'] = "printf 'synthetic-output\\n' >> " + q(str(wrong))
    elif action == 'git_c':
        args['command'] = shlex.join(['git', '-C', str(root / 'wrong'), 'config', 'rig.marker', 'synthetic-output'])
    return [('terminal', args)]


def worker_env(home, cwd, safe_mode):
    # Deliberately give the fixture no account/provider credentials. Preserve proxy/CA settings.
    permitted = ('PATH', 'LANG', 'LC_ALL', 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'REQUESTS_CA_BUNDLE',
                 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy')
    env = {key: os.environ[key] for key in permitted if key in os.environ}
    env.update(HOME=str(home), HERMES_HOME=str(home / '.hermes'), TERMINAL_ENV='local',
               TERMINAL_CWD=str(cwd), PYTHONUNBUFFERED='1', PYTHONDONTWRITEBYTECODE='1',
               NO_PROXY='127.0.0.1,localhost,::1', no_proxy='127.0.0.1,localhost,::1',
               HERMES_SAFE_MODE='1' if safe_mode else '0')
    return env


def sanitize(value, root):
    raw = json.dumps(value, default=str)
    # No real host identifiers or random fixture paths in published evidence.
    for path, replacement in [(str(root), '$FIXTURE'), (str(ROOT), '$RIG'), (str(UPSTREAM), '$UPSTREAM')]:
        raw = raw.replace(path, replacement)
    return json.loads(raw)


def one(case, frozen):
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=case['id'] + '-', dir=RUNTIME) as temp:
        root = Path(temp)
        fixture(root)
        before = {}
        if case.get('action') == 'patch':
            (root / 'wrong/out.txt').write_text('old-output\n')
            before['wrong/out.txt'] = b'old-output\n'
        audit = root / 'audit.jsonl'
        hooks = []
        if case['mechanism'] != 'absent':
            modes = [case['mechanism']] + (['override'] if case.get('second_hook') else [])
            for mode in modes:
                hooks.append({'command': shlex.join([str(PYTHON), str(ROOT / 'gate.py'), '--mode', mode,
                                                     '--audit', str(audit)]),
                              'matcher': '^terminal$', 'timeout': 1, 'fail_closed': True})
        calls = calls_for(case, root)
        with ScriptedModel(calls) as model:
            spec = {'id': case['id'], 'url': model.url, 'hooks': hooks,
                    'consent': case.get('consent', True), 'receipt': str(root / 'worker.json')}
            (root / 'spec.json').write_text(json.dumps(spec))
            # Worker process cwd intentionally differs from the terminal task cwd.
            home = root / 'home'
            home.mkdir()
            cmd = [str(PYTHON), str(ROOT / 'worker.py'), str(root / 'spec.json')]
            proc = subprocess.Popen(cmd, cwd=root, env=worker_env(home, root / case['cwd'], case.get('safe_mode')),
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
            try:
                output, _ = proc.communicate(timeout=55)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                output, _ = proc.communicate()
                raise RuntimeError(case['id'] + ': worker deadline exceeded\n' + output[-6000:])
            if proc.returncode or not (root / 'worker.json').exists():
                raise RuntimeError(case['id'] + ': worker failed\n' + output[-12000:])
            receipt = json.loads((root / 'worker.json').read_text())
            audit_rows = [json.loads(line) for line in audit.read_text().splitlines()] if audit.exists() else []
            observed = effects(root, before)
            errors = check(case, receipt, observed, audit_rows, model.requests, calls, frozen['artifact_content'])
            errors += model.errors
            record = {'id': case['id'], 'classification': case['classification'], 'errors': errors,
                      'expectation_matched': not errors, 'observed_effects': observed,
                      'hook_audit': audit_rows, 'worker': receipt, 'model_requests': model.requests,
                      'metadata_requests': model.metadata_requests,
                      'process_output': output, 'seconds': round(time.monotonic() - started, 3),
                      'command': cmd}
            return sanitize(record, root)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', action='append')
    parser.add_argument('--output', type=Path, default=RUNTIME / 'results.json')
    args = parser.parse_args()
    frozen = contract(ROOT / 'contract.json')
    sources = source_hashes()
    if sys.version_info[:2] != (3, 14):
        raise SystemExit('Run with .runtime/venv/bin/python (3.14 required)')
    if git(UPSTREAM, 'rev-parse', 'HEAD') != frozen['upstream'] or git(UPSTREAM, 'status', '--porcelain', '--untracked-files=no'):
        raise SystemExit('Upstream identity or tracked-source integrity mismatch')
    cases = [c for c in frozen['cases'] if not args.case or c['id'] in args.case]
    if not cases or (args.case and set(args.case) - {c['id'] for c in cases}):
        raise SystemExit('Unknown case')
    results = []
    for case in cases:
        result = one(case, frozen)
        results.append(result)
        (RUNTIME / 'last-case.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({key: result[key] for key in ('id', 'classification', 'expectation_matched', 'errors', 'seconds')}), flush=True)
        if case['id'] == 'absent_wrong' and not result['expectation_matched']:
            raise SystemExit('Invalid absent-gate detector baseline; stopping')
    with tempfile.TemporaryDirectory(prefix='helper-checks-', dir=RUNTIME) as temp:
        directory = Path(temp)
        fault_output = directory / 'faults.json'
        proc = subprocess.run([str(PYTHON), str(ROOT / 'fault_checks.py'), str(fault_output)],
                              env=worker_env(directory, directory, False), cwd=directory,
                              capture_output=True, text=True, timeout=30)
        if proc.returncode:
            raise RuntimeError('Helper fault checks failed: ' + proc.stdout + proc.stderr)
        faults = json.loads(fault_output.read_text())
    if source_hashes() != sources:
        raise SystemExit('Rig sources changed during execution; receipt refused')
    if git(UPSTREAM, 'status', '--porcelain', '--untracked-files=no'):
        raise SystemExit('Tracked upstream sources changed during execution')
    report = {'upstream': frozen['upstream'], 'contract_sha256': CONTRACT_SHA256,
              'python': sys.version.split()[0], 'entry_point': 'run_agent.AIAgent.run_conversation',
              'source_sha256': sources,
              'results': results, 'helper_checks': faults,
              'all_expectations_matched': all(r['expectation_matched'] for r in results)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    if not report['all_expectations_matched']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
