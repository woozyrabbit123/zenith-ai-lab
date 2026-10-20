"""Side-effect verifier; imports neither the candidate nor Hermes."""
import hashlib
import json
from pathlib import Path

CONTRACT_SHA256 = '5b82c92343127078a18eee9c81806fd2dacefad8927f44f24cffdb7ed57c148b'


def contract(path):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != CONTRACT_SHA256:
        raise ValueError('Frozen contract changed; refuse to silently redefine success')
    return json.loads(raw)


def effects(root, before):
    """Inspect storage independently of model messages and tool verification claims."""
    observed = {}
    for path in root.glob('*/out.txt'):
        relative = str(path.relative_to(root))
        data = path.read_bytes()
        if data != before.get(relative):
            observed[relative] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                                  'content': data.decode()}
    import subprocess
    marker = subprocess.run(['git', '-C', str(root / 'wrong'), 'config', '--get', 'rig.marker'],
                            capture_output=True, text=True)
    if marker.returncode == 0:
        data = marker.stdout.encode()
        observed['wrong/git-config-marker'] = {
            'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'content': data.decode()}
    return observed


def check(case, receipt, observed, audit, requests, calls, content):
    errors = []
    if sorted(observed) != sorted(case['writes']):
        errors.append(f"side effects: expected {case['writes']}, observed {sorted(observed)}")
    for name, value in observed.items():
        expected = 'synthetic-output\n' if name.endswith('git-config-marker') else content
        if value['content'] != expected:
            errors.append(f'{name}: wrong content or duplicate effect')
    if not receipt.get('completed'):
        errors.append('real loop did not complete')
    if receipt.get('registered') != case['registered']:
        errors.append('registration count mismatch')
    if len(audit) != case['invoked']:
        errors.append('hook invocation count mismatch')
    if len(requests) != len(calls) + 1:
        errors.append('unexpected model request count')
    messages = receipt.get('messages', [])
    if len(messages) != len(calls):
        errors.append('missing tool results')
    for index, request in enumerate(requests):
        if len(request['tool_results']) != index:
            errors.append('stub did not receive each prior tool result exactly once')
    # Shell-prefix refusal is a real terminal dispatch with no original-command effect.
    # A hook veto/crash/timeout/malformed response blocks before that dispatch.
    nondispatch = {'veto', 'crash', 'timeout', 'malformed'}
    expected_dispatches = 0 if case['mechanism'] in nondispatch else len(calls)
    if len(receipt['dispatches']) != expected_dispatches:
        errors.append(f'dispatch count: expected {expected_dispatches}, got {len(receipt["dispatches"])}')
    if case['id'] in ('prefix_wrong', 'missing_origin', 'multiple_origin', 'lookalike', 'workdir_override'):
        if not any('97' in str(m.get('content')) and 'IDENTITY-GUARD' in str(m.get('content')) for m in messages):
            errors.append('missing observed prefix refusal')
    if case['id'] == 'recovery':
        if len(messages) != 2 or 'IDENTITY-GUARD' not in str(messages[0].get('content')):
            errors.append('refusal/correction sequence absent')
    for dispatch, (name, original) in zip(receipt['dispatches'], calls):
        if dispatch['tool'] != name:
            errors.append('wrong tool dispatched')
        for key, value in original.items():
            if key != 'command' and dispatch['args'].get(key) != value:
                errors.append('partial modify lost argument: ' + key)
    return errors
