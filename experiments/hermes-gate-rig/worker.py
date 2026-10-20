"""One isolated real Hermes conversation; invoked only by run.py."""
import ipaddress
import json
from pathlib import Path
import socket
import sys


def local_network_only():
    original = socket.socket.connect
    original_ex = socket.socket.connect_ex

    def checked(fn):
        def connect(sock, address):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                host = address[0]
                if host != 'localhost' and not ipaddress.ip_address(host).is_loopback:
                    raise PermissionError('Rig worker permits only loopback network')
            return fn(sock, address)
        return connect
    socket.socket.connect = checked(original)
    socket.socket.connect_ex = checked(original_ex)


def main():
    spec = json.loads(Path(sys.argv[1]).read_text())
    local_network_only()
    import hermes_bootstrap  # upstream entry-point bootstrap; no alternate dispatcher
    from agent.shell_hooks import register_from_config
    from hermes_cli.plugins import get_plugin_manager
    from run_agent import AIAgent
    import model_tools

    config = {'hooks': {'pre_tool_call': spec['hooks']}}
    registered = register_from_config(config, accept_hooks=spec['consent'])
    dispatches, post_events = [], []
    original = model_tools.handle_function_call

    def observed(name, args, *a, **kw):
        dispatches.append({'tool': name, 'args': dict(args)})
        return original(name, args, *a, **kw)

    model_tools.handle_function_call = observed
    # Observation only: this callback returns None and never changes tool policy/results.
    def post(**kwargs):
        post_events.append({key: kwargs.get(key) for key in ('tool_name', 'status', 'error_type', 'result')})
    get_plugin_manager()._hooks.setdefault('post_tool_call', []).append(post)
    agent = AIAgent(base_url=spec['url'], api_key='synthetic-not-a-secret', provider='custom',
                    api_mode='chat_completions', model='rig-scripted', max_iterations=8,
                    enabled_toolsets=['terminal', 'file'], quiet_mode=True,
                    session_id='synthetic-' + spec['id'], platform='cli',
                    skip_context_files=True, skip_memory=True, skip_background_review=True,
                    load_soul_identity=False, max_tokens=256, reasoning_config={'enabled': False})
    try:
        result = agent.run_conversation('Execute the scripted synthetic fixture.',
                                        system_message='Synthetic integration test. Follow the scripted tool calls.',
                                        task_id='synthetic-' + spec['id'])
        receipt = {'registered': len(registered), 'dispatches': dispatches, 'post_events': post_events,
                   'completed': result.get('completed'), 'api_calls': result.get('api_calls'),
                   'messages': [m for m in result.get('messages', []) if m.get('role') == 'tool'],
                   'final_response': result.get('final_response')}
        Path(spec['receipt']).write_text(json.dumps(receipt, indent=2, default=str) + '\n')
    finally:
        agent.close()


if __name__ == '__main__':
    main()
