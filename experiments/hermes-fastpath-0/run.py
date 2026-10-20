"""Compare separately scripted baseline and native batching on the same approved fixture."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from fastpath import cell
from observe import CONTRACT_HASH, Writes, contract, safe_snapshot, snapshot
from stub import Model

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT/'.runtime'
PYTHON = RUNTIME/'venv/bin/python'
UPSTREAM = RUNTIME/'upstream'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True,
                                   stderr=subprocess.DEVNULL).strip()


def fixture(root, request_file, case, frozen):
    root.mkdir()
    (root/'.fastpath').mkdir()
    (root/'.fastpath/lock').touch()
    (root/'settings.json').write_text(frozen['before'])
    (root/'notes.txt').write_text(frozen['notes'])
    git(root, 'init', '-q')
    git(root, 'remote', 'add', 'origin', frozen['origin'])
    git(root, 'add', 'settings.json', 'notes.txt')
    env = dict(os.environ, GIT_AUTHOR_DATE='2000-01-01T00:00:00+00:00', GIT_COMMITTER_DATE='2000-01-01T00:00:00+00:00')
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=Synthetic Fixture',
                    '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgsign=false',
                    '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'synthetic settings'], env=env, check=True)
    request = {'operation_id': 'settings-mode-v1', 'root': str(root), 'origin': frozen['origin'],
               'head': git(root, 'rev-parse', 'HEAD'), 'before_sha256': sha(frozen['before'].encode()),
               'after_sha256': sha(frozen['after'].encode()), 'notes_sha256': sha(frozen['notes'].encode())}
    request_file.write_text(json.dumps(request, sort_keys=True))
    if case['id'] == 'precondition':
        (root/'settings.json').write_text(frozen['before'].replace('"draft"', '"locked"'))
    if case['id'] == 'wrong_repo':
        git(root, 'remote', 'set-url', 'origin', 'https://github.com/fixture/wrong.git')
    if case['id'] == 'update_failure':
        root.chmod(0o555)
    return request


def commands(request_file, disconnect=False):
    result = []
    for phase in ('inspect', 'update', 'verify'):
        args = [str(PYTHON), str(ROOT/'recipe.py'), phase, '--request', str(request_file)]
        if disconnect and phase == 'update':
            args.append('--simulate-disconnect-after-write')
        result.append((phase, shlex.join(args)))
    return result


def plan(case, mode, request_file):
    regular = commands(request_file)
    if mode == 'fastpath':
        cells = [cell(commands(request_file, case['id'] == 'disconnect'))]
        if case['id'] in ('repeat', 'disconnect'):
            cells.append(cell(regular))
        return [('execute_code', {'code': code}) for code in cells]
    if case['id'] in ('wrong_cwd', 'wrong_repo', 'precondition'):
        phases = regular[:1]
    elif case['id'] in ('update_failure', 'terminal_denied'):
        phases = regular[:2]
    elif case['id'] == 'repeat':
        phases = regular * 2
    elif case['id'] == 'disconnect':
        phases = commands(request_file, True)[:2] + regular[1:]
    else:
        phases = regular
    return [('terminal', {'command': command, 'timeout': 10}) for _, command in phases]


def environment(home, cwd):
    keep = ('PATH', 'LANG', 'LC_ALL', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
            'http_proxy', 'https_proxy', 'all_proxy', 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'REQUESTS_CA_BUNDLE')
    env = {key: os.environ[key] for key in keep if key in os.environ}
    temp = home/'tmp'
    temp.mkdir()
    env.update(HOME=str(home), HERMES_HOME=str(home/'.hermes'), TMPDIR=str(temp), TERMINAL_CWD=str(cwd),
               TERMINAL_ENV='local', PYTHONUNBUFFERED='1', PYTHONDONTWRITEBYTECODE='1',
               NO_PROXY='127.0.0.1,localhost,::1', no_proxy='127.0.0.1,localhost,::1')
    return env


def result_status(worker):
    if worker['policy_denials']:
        return 'policy_refused'
    terminals = [row for row in worker['dispatches'] if row['tool'] == 'terminal']
    if not terminals:
        return 'no_terminal_dispatch'
    result = terminals[-1]['result']
    if isinstance(result, str):
        result = json.loads(result)
    try:
        return json.loads(result.get('output', ''))['status']
    except (ValueError, KeyError):
        return 'unparsed_failure'


def run_one(case, mode, control, frozen):
    root, request_file = control/'repo', control/'request.json'
    fixture(root, request_file, case, frozen)
    home = control/('home-' + mode)
    home.mkdir()
    cwd = control/'wrong-cwd' if case['id'] == 'wrong_cwd' else root
    cwd.mkdir(exist_ok=True)
    before = snapshot(root)
    calls = plan(case, mode, request_file)
    watch = Writes(root)
    start = time.monotonic()
    try:
        with Model(calls) as model:
            output = control/(mode+'.json')
            spec = {'case': case['id'], 'mode': mode, 'root': str(root), 'recipe': str(ROOT/'recipe.py'),
                    'url': model.url, 'output': str(output)}
            spec_file = control/(mode+'-spec.json')
            spec_file.write_text(json.dumps(spec))
            proc = subprocess.Popen([str(PYTHON), str(ROOT/'worker.py'), str(spec_file)], cwd=cwd,
                                    env=environment(home, cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, start_new_session=True)
            try:
                log, _ = proc.communicate(timeout=65)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                log, _ = proc.communicate()
                raise RuntimeError(case['id']+'/'+mode+': deadline exceeded\n'+log[-6000:])
            if proc.returncode or not output.exists():
                raise RuntimeError(case['id']+'/'+mode+': worker failed\n'+log[-12000:])
            worker = json.loads(output.read_text())
            requests, stub_errors, probes = model.requests, model.errors, model.metadata
        events = watch.finish()
        after = snapshot(root)
    finally:
        root.chmod(0o755)
    writes = sum(e['directory']=='.' and e['name']=='settings.json' and bool(e['mask'] & 0x80) for e in events)
    status = result_status(worker)
    errors = list(stub_errors)
    if not worker['completed'] or worker['api_calls'] != len(requests):
        errors.append('real conversation did not finish with the counted model responses')
    expected_turns = case[mode+'_responses']
    if len(requests) != expected_turns or len(requests) != len(calls)+1:
        errors.append(f'model responses expected {expected_turns}, observed {len(requests)}')
    if writes != case['writes']:
        errors.append(f'settings replacements expected {case["writes"]}, observed {writes}')
    if status != case['status']:
        errors.append(f'status expected {case["status"]}, observed {status}')
    if after.get('notes.txt') != before['notes.txt']:
        errors.append('neighbour file changed')
    allowed = {'settings.json', 'notes.txt', '.fastpath/lock', '.fastpath/receipt.json'}
    if set(after)-allowed:
        errors.append('unexpected file or staging file left behind')
    receipt = json.loads(after['.fastpath/receipt.json']) if '.fastpath/receipt.json' in after else None
    if (receipt or {}).get('state') != case['receipt']:
        errors.append('durable receipt state mismatch')
    if case['status'] == 'verified' and after.get('settings.json') != frozen['after'].encode():
        errors.append('successful final bytes differ from independent contract')
    if not case['writes'] and after.get('settings.json') != before['settings.json']:
        errors.append('settings changed on a refused/failed operation')
    if case['status'] in ('refused', 'policy_refused') and after != before:
        errors.append('refused operation changed monitored filesystem')
    if mode == 'fastpath' and (len(worker['native_code_approval_checks']) != len(calls)
                               or not all(a['approved'] for a in worker['native_code_approval_checks'])):
        errors.append('native execute_code approval path not observed unchanged')
    record = {'mode': mode, 'status': status, 'errors': errors, 'settings_replacements': writes,
              'model_responses': len(requests), 'total_dispatches': len(worker['dispatches']),
              'terminal_dispatches': sum(r['tool']=='terminal' for r in worker['dispatches']),
              'model_visible_tool_bytes': sum(len(m['content'].encode()) for m in worker['tool_messages']),
              'model_request_bytes': sum(r['request_bytes'] for r in requests),
              'cumulative_tool_content_bytes': sum(r['tool_content_bytes'] for r in requests),
              'seconds': round(time.monotonic()-start, 3), 'worker': worker, 'model_requests': requests,
              'metadata_probes': probes, 'filesystem_events': events, 'filesystem': safe_snapshot(after), 'log': log}
    shutil.rmtree(root)
    return record, after


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', action='append')
    parser.add_argument('--output', type=Path, default=RUNTIME/'results.json')
    args = parser.parse_args()
    frozen = contract(ROOT/'contract.json')
    if sys.version_info[:2] != (3,14) or git(UPSTREAM, 'rev-parse', 'HEAD') != frozen['upstream']:
        raise SystemExit('Expected task-local Python 3.14 and pinned upstream')
    if git(UPSTREAM, 'status', '--porcelain', '--untracked-files=no'):
        raise SystemExit('Tracked upstream changes refused')
    paths = list(ROOT.glob('*.py')) + [ROOT/'contract.json']
    sources = {p.name: sha(p.read_bytes()) for p in paths}
    cases = [c for c in frozen['cases'] if not args.case or c['id'] in args.case]
    if not cases or (args.case and set(args.case)-{c['id'] for c in cases}):
        raise SystemExit('Unknown case')
    results=[]
    for case in cases:
        with tempfile.TemporaryDirectory(prefix=case['id']+'-', dir=RUNTIME) as temp:
            control=Path(temp)
            baseline, a = run_one(case, 'baseline', control, frozen)
            fastpath, b = run_one(case, 'fastpath', control, frozen)
            errors=baseline['errors']+fastpath['errors']
            if a != b:
                errors.append('baseline/fastpath monitored filesystem bytes differ')
            record={'case':case['id'],'baseline':baseline,'fastpath':fastpath,'errors':errors,
                    'byte_identical_filesystem':a==b}
            raw=json.dumps(record)
            for old,new in [(str(control),'$FIXTURE'),(str(ROOT),'$EXPERIMENT')]:
                raw=raw.replace(old,new)
            results.append(json.loads(raw))
            (RUNTIME/'last-case.json').write_text(json.dumps(results[-1],indent=2)+'\n')
            print(json.dumps({'case':case['id'],'responses':[baseline['model_responses'],fastpath['model_responses']],
                              'settings_replacements':[baseline['settings_replacements'],fastpath['settings_replacements']],
                              'errors':errors}),flush=True)
            if errors:
                break
    if sources != {p.name:sha(p.read_bytes()) for p in paths}:
        raise SystemExit('Sources changed during the measurement')
    report={'upstream':frozen['upstream'],'contract_sha256':CONTRACT_HASH,'source_sha256':sources,
            'entry_point':'run_agent.AIAgent.run_conversation','results':results,'all_expectations_matched':all(not r['errors'] for r in results)}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    if not report['all_expectations_matched']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
