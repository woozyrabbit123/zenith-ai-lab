"""Generate a native execute_code cell. All actions still use Hermes terminal RPC."""
import json


def cell(commands):
    return '''from hermes_tools import terminal
import json
steps = []
for phase, command in ''' + repr(commands) + ''':
    result = terminal(command, timeout=10)
    if isinstance(result, str):
        result = json.loads(result)
    if result.get("error") or result.get("exit_code") != 0:
        steps.append({"step": phase, "ok": False, "terminal_result": result})
        break
    observed = json.loads(result["output"])
    steps.append(observed)
    if not observed.get("ok"):
        break
print(json.dumps({"ok": len(steps) == 3 and all(s.get("ok") for s in steps), "steps": steps}, sort_keys=True))
'''
