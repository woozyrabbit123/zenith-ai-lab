"""Read-only candidate impact against three explicitly scoped PUBLIC lab files."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

COMMIT='e723864c0cdad9ea2c86ee505d28bcbe679472aa'
FILES=('operator_recipe.py','native_smoke.py','onecall.py')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,required=True);p.add_argument('--work',type=Path,required=True)
    args=p.parse_args()
    origin=subprocess.check_output(['git','-C',str(args.repo),'remote','get-url','origin'],text=True).strip()
    if origin!='https://github.com/woozyrabbit123/zenith-ai-lab.git':
        raise SystemExit('wrong public origin')
    args.work.mkdir();root=args.work/'public-source';root.mkdir()
    hashes={}
    for name in FILES:
        data=subprocess.check_output(['git','-C',str(args.repo),'show',COMMIT+':experiments/sentinel-onecall-0/'+name])
        (root/name).write_bytes(data);hashes[name]=hashlib.sha256(data).hexdigest()
    result=subprocess.run([sys.executable,str(Path(__file__).with_name('impact.py')),'trace','--root',str(root),
                           '--symbol','operator_recipe.cell','--out',str(args.work/'derived')],capture_output=True,timeout=35)
    report=json.loads(result.stdout)
    assert result.returncode==0 and report['mechanical']=='PASS',report
    assert {c['symbol'] for c in report['candidates']}=={'native_smoke.main','native_smoke.<module>'}
    assert hashes=={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in FILES}
    receipt=dict(question='Which scoped native-smoke entrypoints need review after operator_recipe.cell changes?',
                 public_repo='woozyrabbit123/zenith-ai-lab',public_commit=COMMIT,source_hashes=hashes,
                 scope='Exactly three exported public files; no whole-repository or test-coverage claim.',
                 project_code_executed=False,sources_unchanged=True,report=report)
    sys.stdout.write(json.dumps(receipt,sort_keys=True,indent=2)+'\n')


if __name__=='__main__':
    main()
