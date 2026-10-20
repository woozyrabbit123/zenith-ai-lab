"""Execute upstream dispatch-helper fault cases, not simulated source conclusions."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch


def main():
    # No owner config or credentials are loaded; the parent runs this in a clean environment.
    from worker import local_network_only
    local_network_only()
    from agent.tool_executor import _pre_tool_block
    from agent.agent_runtime_helpers import _pre_tool_block_message
    from hermes_cli.plugins import _get_pre_tool_call_directive_details

    args = {'command': 'synthetic-original', 'workdir': '/synthetic/workdir', 'timeout': 5}
    agent = SimpleNamespace(session_id='synthetic-fault')
    ref = SimpleNamespace(name='terminal', args=args, task_id='synthetic-task', call_id='synthetic-call', trace=[])
    records = []
    with patch('hermes_cli.plugins._dispatch_pre_tool_call_hooks', side_effect=RuntimeError('synthetic dispatcher fault')) as injected:
        a = _pre_tool_block(agent, ref)
        b = _pre_tool_block_message(agent, 'terminal', args, 'synthetic-task', 'synthetic-call', [])
    assert injected.call_count == 2
    for name, result in [('tool_executor._pre_tool_block', a), ('agent_runtime_helpers._pre_tool_block_message', b)]:
        assert result[0] is None and result[1] is args
        records.append({'path': name, 'injected': 'dispatcher RuntimeError', 'block': None,
                        'original_args_returned': True, 'classification': 'known_gap',
                        'level': 'actual helper execution, not a full-loop tool effect'})
    changes = [{'action': 'modify', 'args': {'command': 'first'}},
               {'action': 'modify', 'args': {'command': 'second'}}]
    with patch('hermes_cli.lifecycle.invoke_hook', return_value=changes):
        merged = _get_pre_tool_call_directive_details('terminal', args).modified_args
    assert merged == {**args, 'command': 'second'}
    records.append({'path': '_get_pre_tool_call_directive_details', 'observed_args': merged,
                    'classification': 'merge_and_later_override_observed'})
    Path(sys.argv[1]).write_text(json.dumps(records, indent=2) + '\n')
    print('3 upstream fault/merge checks observed; no downstream tools executed by this helper test')


if __name__ == '__main__':
    main()
