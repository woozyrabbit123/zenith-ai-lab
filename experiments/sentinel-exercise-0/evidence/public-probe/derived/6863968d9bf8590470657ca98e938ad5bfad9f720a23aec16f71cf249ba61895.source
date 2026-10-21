"""Generate one native Hermes execute_code cell; never launch a worker or install."""
import shlex


def cell(python, onecall, root, query, out):
    command = shlex.join([python, onecall, 'evidence', '--root', root, '--query', query, '--out', out])
    return ('from hermes_tools import terminal\n'
            'import json\n'
            f'result = terminal({command!r}, timeout=40)\n'
            'if isinstance(result, str): result = json.loads(result)\n'
            'print(json.dumps({"exit_code": result.get("exit_code"), "error": result.get("error"), '
            '"packet": result.get("output", "")}))\n')
