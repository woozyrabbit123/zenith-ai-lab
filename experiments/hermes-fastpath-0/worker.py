"""Real upstream conversation with observation-only dispatch/approval instrumentation."""
import ipaddress
import json
from pathlib import Path
import shlex
import socket
import sys


def local_network_only():
    def guard(original):
        def connect(sock, address):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                if address[0] != 'localhost' and not ipaddress.ip_address(address[0]).is_loopback:
                    raise PermissionError('Fixture worker network is loopback only')
            return original(sock, address)
        return connect
    socket.socket.connect = guard(socket.socket.connect)
    socket.socket.connect_ex = guard(socket.socket.connect_ex)


def main():
    spec = json.loads(Path(sys.argv[1]).read_text())
    local_network_only()
    import hermes_bootstrap
    import model_tools
    import tools.approval
    from hermes_cli.plugins import get_plugin_manager
    from run_agent import AIAgent

    dispatches, approvals, denials, injections = [], [], [], []
    original_dispatch = model_tools.handle_function_call
    original_guard = tools.approval.check_execute_code_guard

    def observed_guard(*args, **kwargs):
        result = original_guard(*args, **kwargs)
        approvals.append({'approved': result.get('approved'), 'user_approved': result.get('user_approved', False)})
        return result
    tools.approval.check_execute_code_guard = observed_guard

    def phase_of(name, args):
        if name != 'terminal':
            return None
        tokens = shlex.split(args.get('command', ''))
        script = spec['recipe']
        return tokens[tokens.index(script)+1] if script in tokens else None

    def policy(**kwargs):
        if spec['case'] == 'terminal_denied' and phase_of(kwargs.get('tool_name'), kwargs.get('args', {})) == 'update':
            denials.append('update')
            return {'action': 'block', 'message': 'synthetic policy refusal: update denied'}
    get_plugin_manager()._hooks.setdefault('pre_tool_call', []).append(policy)

    def observed_dispatch(name, args, *a, **kw):
        row = {'tool': name, 'phase': phase_of(name, args), 'args': dict(args)}
        dispatches.append(row)
        result = original_dispatch(name, args, *a, **kw)
        row['result'] = result
        if row['phase'] == 'update' and spec['case'] in ('verify_tamper', 'verify_missing') and not injections:
            target = Path(spec['root'])/'settings.json'
            if spec['case'] == 'verify_tamper':
                target.write_bytes(target.read_bytes().replace(b'"limit": 4', b'"limit": 999'))
            else:
                target.unlink()
            injections.append(spec['case'])
        return result
    model_tools.handle_function_call = observed_dispatch
    agent = AIAgent(base_url=spec['url'], api_key='synthetic-not-a-secret', provider='custom',
                    api_mode='chat_completions', model='fastpath-scripted', max_iterations=10,
                    enabled_toolsets=['terminal', 'code_execution'], quiet_mode=True,
                    session_id='synthetic-' + spec['case'] + '-' + spec['mode'], platform='cli',
                    skip_context_files=True, skip_memory=True, skip_background_review=True,
                    load_soul_identity=False, max_tokens=8192, reasoning_config={'enabled': False})
    try:
        result = agent.run_conversation('Run the approved synthetic settings operation.',
                                        system_message='Synthetic deterministic integration fixture.',
                                        task_id=agent.session_id)
        receipt = {'completed': result.get('completed'), 'api_calls': result.get('api_calls'),
                   'tool_messages': [m for m in result.get('messages', []) if m.get('role') == 'tool'],
                   'dispatches': dispatches, 'native_code_approval_checks': approvals,
                   'policy_denials': denials, 'external_fault_injections': injections}
        Path(spec['output']).write_text(json.dumps(receipt, indent=2, default=str)+'\n')
    finally:
        agent.close()


if __name__ == '__main__':
    main()
