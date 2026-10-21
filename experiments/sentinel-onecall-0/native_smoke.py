"""Optional real Hermes native-tool smoke test using an ALREADY provisioned runtime.

No bootstrap/install, no model endpoint, no provider task launch. Run this script
with the existing Hermes environment's Python and provide its reviewed source path.
"""
import argparse
import contextlib
import ipaddress
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

from operator_recipe import cell


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--upstream', type=Path, required=True)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--work', type=Path, required=True)
    args = p.parse_args()
    args.work.mkdir()
    (args.work/'tmp').mkdir()
    os.environ.update(HERMES_HOME=str(args.work/'profile'), TERMINAL_CWD=str(args.work),
                      TERMINAL_ENV='local', TMPDIR=str(args.work/'tmp'))
    # Model/provider connections are disallowed in this smoke process.
    original_connect = socket.socket.connect
    def local_only(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            if address[0] != 'localhost' and not ipaddress.ip_address(address[0]).is_loopback:
                raise PermissionError('Smoke fixture permits local RPC only')
        return original_connect(sock, address)
    socket.socket.connect = local_only
    sys.path.insert(0, str(args.upstream))
    import hermes_bootstrap
    import model_tools
    from tools.code_kernel import shutdown_all_kernels
    from tools.terminal_tool import _atexit_cleanup
    calls = []
    original_dispatch = model_tools.handle_function_call
    def observed(name, *a, **kw):
        calls.append(name)
        return original_dispatch(name, *a, **kw)
    model_tools.handle_function_call = observed
    with contextlib.redirect_stdout(sys.stderr):
        model_tools.get_tool_definitions(enabled_toolsets=['terminal', 'code_execution'])
    code = cell(sys.executable, str(Path(__file__).resolve().with_name('onecall.py')),
                str(args.input), 'ship blue', str(args.work/'derived'))
    try:
        response = json.loads(model_tools.handle_function_call('execute_code', {'code': code},
                              task_id='synthetic-onecall', enabled_tools=['terminal']))
        text = response.get('output') or response.get('stdout', '')
        inner = json.loads(text)
        packet = json.loads(inner['packet'])
        assert inner['exit_code'] == 0 and packet['mechanical'] == 'PASS', response
        assert calls == ['execute_code', 'terminal'], calls
        result = dict(hermes_commit=subprocess.check_output(['git','-C',str(args.upstream),'rev-parse','HEAD'],text=True).strip(),
                      python=sys.version.split()[0], dispatches=calls, model_api_calls=0,
                      native_tool_status=response.get('status'), packet=packet,
                      original_input='synthetic demo sources only',
                      limits='Existing cached upstream; not Sentinel laptop or its v0.22.2 runtime.')
        print(json.dumps(result, indent=2))
    finally:
        shutdown_all_kernels()
        _atexit_cleanup()


if __name__ == '__main__':
    main()
