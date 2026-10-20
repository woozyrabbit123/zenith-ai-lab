"""Focused independent detector and refusal checks; integration uses the real loop."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from observe import Writes, contract, snapshot
from run import ROOT, PYTHON, fixture


class SafetyChecks(unittest.TestCase):
    def setUp(self):
        self.frozen = contract(ROOT/'contract.json')

    def test_changed_contract_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'contract.json'
            path.write_text('{"cases":[]}')
            with self.assertRaises(ValueError):
                contract(path)

    def test_kernel_observes_duplicate_replacements(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'.fastpath').mkdir()
            (root/'settings.json').write_text('same')
            watch=Writes(root)
            for i in range(2):
                staged=root/('stage'+str(i))
                staged.write_text('same')
                os.replace(staged,root/'settings.json')
            events=watch.finish()
            self.assertEqual(sum(e['name']=='settings.json' and bool(e['mask']&0x80) for e in events),2)

    def run_recipe(self, phase, request, root):
        proc=subprocess.run([str(PYTHON),str(ROOT/'recipe.py'),phase,'--request',str(request)],
                            cwd=root,capture_output=True,text=True)
        return proc.returncode,json.loads(proc.stdout)

    def test_unowned_after_state_refused_without_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            control=Path(temp)
            root,request=control/'repo',control/'request.json'
            fixture(root,request,{'id':'success'},self.frozen)
            (root/'settings.json').write_text(self.frozen['after'])
            before=snapshot(root)
            code,result=self.run_recipe('inspect',request,root)
            self.assertNotEqual(code,0)
            self.assertEqual(result['status'],'refused')
            self.assertEqual(snapshot(root),before)

    def test_changed_neighbour_refused_without_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            control=Path(temp)
            root,request=control/'repo',control/'request.json'
            fixture(root,request,{'id':'success'},self.frozen)
            (root/'notes.txt').write_text('unexpected neighbour')
            before=snapshot(root)
            code,result=self.run_recipe('update',request,root)
            self.assertNotEqual(code,0)
            self.assertEqual(result['status'],'refused')
            self.assertEqual(snapshot(root),before)

    def test_update_preserves_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            control=Path(temp)
            root,request=control/'repo',control/'request.json'
            fixture(root,request,{'id':'success'},self.frozen)
            (root/'settings.json').chmod(0o640)
            code,result=self.run_recipe('update',request,root)
            self.assertEqual(code,0)
            self.assertTrue(result['wrote_settings'])
            self.assertEqual((root/'settings.json').stat().st_mode & 0o777,0o640)


if __name__=='__main__':
    unittest.main()
