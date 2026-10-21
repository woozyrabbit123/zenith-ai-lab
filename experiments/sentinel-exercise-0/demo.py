#!/usr/bin/env python3
"""Reproduce a synthetic regression or pinned public-code probe. No installation."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent
PUBLIC_PIN='b4da1ae1c42e8654a3384b2ea971cc1663b193446872a8f07a9d75b6a6213dc1'
PUBLIC_COMMIT='e723864c0cdad9ea2c86ee505d28bcbe679472aa'


def encode(value):
    return (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()


def measured(root,target,out,expected):
    p=subprocess.run([sys.executable,str(HERE/'exercise.py'),'run','--root',str(root),
                      '--target',target,'--out',str(out)],capture_output=True,timeout=25)
    assert p.returncode==expected,(p.returncode,p.stdout,p.stderr)
    packet=json.loads(p.stdout)
    assert packet['integrity']=='PASS',packet
    assert p.stdout==(out/'packet.json').read_bytes()
    return packet


def synthetic(work):
    root=work/'input';root.mkdir()
    engine=root/'engine.py'
    engine.write_text('def validate(x):\n    return x >= 0\n')
    (root/'test_flow.py').write_text('import unittest\nfrom engine import validate as check\nclass Tests(unittest.TestCase):\n    def test_boundary(self):\n        self.assertFalse(check(0))\n    def test_green_decoy(self):\n        self.assertTrue(True)\n')
    before=measured(root,'engine.py:validate',work/'before',1)
    assert before['status']=='OBSERVED_WITH_FAILURE' and before['test_result']=='FAIL'
    # The demo author explicitly edits this disposable synthetic fixture between runs.
    engine.write_text('def validate(x):\n    return x > 0\n')
    after=measured(root,'engine.py:validate',work/'after',0)
    assert after['status']=='OBSERVED' and after['test_result']=='PASS'
    assert before['target']['source_sha256']!=after['target']['source_sha256']
    assert before['target']['code_sha256']!=after['target']['code_sha256']
    for packet in (before,after):
        assert packet['observed_tests']==['test_flow.Tests.test_boundary']
        assert packet['not_observed_tests']==['test_flow.Tests.test_green_decoy']
    return dict(kind='synthetic boundary regression',python=sys.version.split()[0],
                before=before,after=after,fix='Demo author changed >= 0 to > 0 between runs; no autonomous repair.',
                meaning='The real failing/passing test entered selected code; the green decoy did not. Assertion quality remains unproven.')


def public(work):
    root=work/'input';root.mkdir()
    fixture=HERE/'fixtures'/'public'
    source=(fixture/'operator_recipe.py').read_bytes()
    assert hashlib.sha256(source).hexdigest()==PUBLIC_PIN
    for name in ('operator_recipe.py','test_recipe.py'):
        shutil.copyfile(fixture/name,root/name)
    packet=measured(root,'operator_recipe.py:cell',work/'derived',0)
    assert packet['target']['source_sha256']==PUBLIC_PIN
    assert packet['observed_tests']==['test_recipe.RecipeTests.test_argv_roundtrip','test_recipe.RecipeTests.test_one_terminal_call']
    assert packet['not_observed_tests']==['test_recipe.RecipeTests.test_green_decoy']
    assert packet['test_result']=='PASS'
    return dict(kind='actual public-source direct-test probe',python=sys.version.split()[0],
                public_repo='woozyrabbit123/zenith-ai-lab',public_commit=PUBLIC_COMMIT,
                source_path='experiments/sentinel-onecall-0/operator_recipe.py',source_sha256=PUBLIC_PIN,
                project_code_executed=True,generated_code_executed=False,hermes_rpc_count=0,
                test_origin='New trusted direct tests; not the upstream subprocess suite or laptop.',packet=packet)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--public-probe',action='store_true')
    args=parser.parse_args();args.work.mkdir(parents=True,exist_ok=False)
    receipt=(public if args.public_probe else synthetic)(args.work)
    raw=encode(receipt);(args.work/'receipt.json').write_bytes(raw)
    sys.stdout.buffer.write(raw)


if __name__=='__main__':main()
