"""Synthetic alias impact proof; invokes the actual CLI without executing sources."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work',type=Path,required=True)
    args=p.parse_args();args.work.mkdir()
    root=args.work/'input';root.mkdir()
    fixtures={'engine.py':'def validate(x):\n    return x > 0\n',
              'pipeline.py':'from engine import validate as check\r\ndef run(x):\r\n    café = "é"; return check(x)\r\n',
              'test_flow.py':'from pipeline import run as launch\ndef test_good():\n    assert launch(1)\n'}
    for name,text in fixtures.items():
        (root/name).write_bytes(text.encode())
    before={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(root.iterdir())}
    out=args.work/'derived'
    command=[sys.executable,str(HERE/'impact.py'),'trace','--root',str(root),'--symbol','engine.validate','--out',str(out)]
    run=subprocess.run(command,capture_output=True,timeout=35)
    result=json.loads(run.stdout)
    assert run.returncode==0 and result['mechanical']=='PASS',result
    assert {c['symbol'] for c in result['candidates']}=={'pipeline.run','test_flow.test_good'}
    grep=subprocess.run(['rg','-n','validate','.'],cwd=root,capture_output=True,text=True,check=True).stdout
    assert 'test_flow.py' not in grep
    assert before=={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(root.iterdir())}
    receipt=dict(question='Which candidate callers and tests need review after changing engine.validate?',
                 report_bytes=len(run.stdout),sources_unchanged=True,source_hashes=before,
                 grep_command='rg -n validate .',grep_output=grep,report=result)
    (args.work/'receipt.json').write_bytes(encode(receipt))
    (args.work/'brief.md').write_text('# Candidate impact of engine.validate\n\n'
        'Review `pipeline.run`, then candidate test `test_flow.test_good`. The first calls '
        '`check(x)`, an import alias for `engine.validate`; the second calls `launch(1)`, '
        'an import alias for `pipeline.run`. Name grep misses the test call.\n\n'
        'These are syntactic candidates, not runtime reachability or coverage proof. '
        'No project code or tests were executed. UTF-8/CRLF source bytes stayed unchanged.\n\n'
        '[Exact call-site evidence](derived/report.json) · [full graph](derived/graph.json)\n')
    sys.stdout.buffer.write(encode(receipt))


def encode(obj):
    return (json.dumps(obj,sort_keys=True,indent=2,ensure_ascii=True)+'\n').encode()


if __name__=='__main__':
    main()
