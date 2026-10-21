"""Independent end-to-end acceptance tests; every executed target is synthetic."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
CLI=HERE/'exercise.py'


class ExerciseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.root=self.base/'input';self.root.mkdir()
        self.out=self.base/'derived'
        self.put('engine.py','def validate(x):\n    return x > 0\n')
        self.put('test_flow.py','import unittest\nfrom engine import validate as check\nclass Tests(unittest.TestCase):\n    def test_real(self):\n        self.assertTrue(check(1))\n    def test_decoy(self):\n        self.assertTrue(True)\n')

    def put(self,name,text):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(text.encode())

    def call(self,target='engine.py:validate',extra=(),root=None,out=None):
        p=subprocess.run([sys.executable,str(CLI),'run','--root',str(root or self.root),'--target',target,
                          '--out',str(out or self.out),*map(str,extra)],capture_output=True,timeout=25)
        self.assertTrue(p.stdout,p.stderr.decode());self.assertLessEqual(len(p.stdout),8192)
        return p.returncode,json.loads(p.stdout)

    def result(self):
        return json.loads((self.out/'result.json').read_bytes())

    def test_real_alias_and_green_decoy_are_distinguished(self):
        before={f.name:f.read_bytes() for f in self.root.iterdir()}
        code,r=self.call();self.assertEqual(code,0,r)
        self.assertEqual(r['status'],'OBSERVED');self.assertEqual(r['test_result'],'PASS')
        self.assertEqual(r['observed_tests'],['test_flow.Tests.test_real'])
        self.assertIn('test_flow.Tests.test_decoy',r['not_observed_tests'])
        self.assertEqual(r['integrity'],'PASS')
        self.assertEqual(before,{f.name:f.read_bytes() for f in self.root.iterdir()})
        self.assertFalse((self.root/'__pycache__').exists())
        self.assertTrue(r['target']['code_sha256'])
        self.assertEqual(r['target']['source_sha256'],hashlib.sha256(before['engine.py']).hexdigest())

    def test_dynamic_method_dispatch_is_observed(self):
        self.put('engine.py','class Service:\n    def validate(self,x):\n        return x > 0\n')
        self.put('test_flow.py','import unittest\nfrom engine import Service\nclass Tests(unittest.TestCase):\n    def test_real(self):\n        method=getattr(Service(),"validate")\n        self.assertTrue(method(1))\n')
        code,r=self.call('engine.py:Service.validate')
        self.assertEqual(code,0,r);self.assertEqual(r['observed_tests'],['test_flow.Tests.test_real'])

    def test_only_decoy_is_not_observed(self):
        self.put('test_flow.py','import unittest\nclass Tests(unittest.TestCase):\n    def test_green(self):\n        self.assertTrue(True)\n')
        code,r=self.call();self.assertEqual(code,1,r)
        self.assertEqual(r['status'],'NOT_OBSERVED_IN_SCOPE');self.assertEqual(r['test_result'],'PASS')
        self.assertEqual(r['observed_tests'],[])

    def test_discovery_call_is_not_credited_to_test(self):
        self.put('test_flow.py','import unittest\nfrom engine import validate\nvalidate(1)\nclass Tests(unittest.TestCase):\n    def test_green(self):\n        self.assertTrue(True)\n')
        code,r=self.call();self.assertEqual(code,1,r)
        self.assertEqual(r['observed_tests'],[]);self.assertGreater(r['unassigned_call_events'],0)

    def test_same_name_in_another_file_is_not_selected(self):
        self.put('other.py','def validate(x):\n    return True\n')
        self.put('test_flow.py','import unittest\nfrom other import validate\nclass Tests(unittest.TestCase):\n    def test_other(self):\n        self.assertTrue(validate(1))\n')
        code,r=self.call();self.assertEqual(code,1,r);self.assertEqual(r['observed_tests'],[])

    def test_failure_subtest_skip_and_expected_failure_remain_explicit(self):
        self.put('test_flow.py','import unittest\nfrom engine import validate\nclass Tests(unittest.TestCase):\n    def test_sub(self):\n        with self.subTest(case=1):\n            self.assertFalse(validate(1))\n    @unittest.skip("synthetic")\n    def test_skip(self):\n        validate(1)\n    @unittest.expectedFailure\n    def test_xfail(self):\n        self.assertFalse(validate(1))\n')
        code,r=self.call();self.assertEqual(code,1,r);self.assertEqual(r['test_result'],'FAIL')
        rows={t['id']:t for t in self.result()['tests']}
        self.assertEqual(rows['test_flow.Tests.test_sub']['outcome'],'FAIL')
        self.assertEqual(rows['test_flow.Tests.test_skip']['outcome'],'SKIP')
        self.assertEqual(rows['test_flow.Tests.test_skip']['call_events'],0)
        self.assertEqual(rows['test_flow.Tests.test_xfail']['outcome'],'XFAIL')

    def test_source_mutation_invalidates_observation(self):
        self.put('test_flow.py','import unittest\nfrom pathlib import Path\nfrom engine import validate\nclass Tests(unittest.TestCase):\n    def test_mutate(self):\n        validate(1)\n        Path("engine.py").write_text("changed")\n')
        code,r=self.call();self.assertEqual(code,2,r);self.assertEqual(r['integrity'],'FAIL')
        self.assertNotEqual(r['status'],'OBSERVED')

    def test_profiler_disable_invalidates_proof(self):
        self.put('test_flow.py','import unittest,sys\nfrom engine import validate\nclass Tests(unittest.TestCase):\n    def test_disable(self):\n        sys.setprofile(None)\n        validate(1)\n')
        code,r=self.call();self.assertEqual(code,2,r)
        self.assertEqual(r['status'],'INCOMPLETE');self.assertIn('PROFILE_CHANGED',r['gaps'])

    def test_code_replacement_does_not_count_original_function(self):
        self.put('test_flow.py','import unittest,engine\nengine.validate=lambda x: True\nclass Tests(unittest.TestCase):\n    def test_new(self):\n        self.assertTrue(engine.validate(1))\n')
        code,r=self.call();self.assertEqual(code,1,r);self.assertEqual(r['observed_tests'],[])

    def test_test_wall_and_output_limits_refuse_clean_proof(self):
        code,r=self.call(extra=('--tests',1));self.assertEqual(code,2,r);self.assertEqual(r['status'],'INCOMPLETE')
        self.put('test_flow.py','import unittest,time\nclass Tests(unittest.TestCase):\n    def test_sleep(self):\n        time.sleep(3)\n')
        code,r=self.call(out=self.base/'timeout',extra=('--wall',0.2))
        self.assertEqual(code,2,r);self.assertEqual(r['status'],'INCOMPLETE')
        self.put('test_flow.py','import unittest\nclass Tests(unittest.TestCase):\n    def test_log(self):\n        print("x"*100000)\n')
        code,r=self.call(out=self.base/'log',extra=('--log-bytes',4096))
        self.assertEqual(code,2,r);self.assertEqual(r['status'],'INCOMPLETE')

    def test_input_refusal_and_existing_output_preserve_inputs(self):
        marker=self.base/'SHOULD_NOT_RUN'
        self.put('test_flow.py',f'from pathlib import Path\nPath({str(marker)!r}).touch()\n')
        (self.root/'escape.py').symlink_to('/etc/passwd')
        code,r=self.call();self.assertEqual(code,2,r);self.assertFalse(marker.exists())
        before=(self.out/'manifest.json').read_bytes()
        self.assertEqual(self.call()[0],2);self.assertEqual((self.out/'manifest.json').read_bytes(),before)
        alias=self.base/'alias';alias.symlink_to(self.root,target_is_directory=True)
        self.assertEqual(self.call(root=str(alias/'..'/'input'),out=self.base/'bad')[0],2)

    def test_missing_or_ambiguous_target_never_executes_tests(self):
        marker=self.base/'SHOULD_NOT_RUN'
        self.put('test_flow.py',f'from pathlib import Path\nPath({str(marker)!r}).touch()\n')
        code,r=self.call('engine.py:missing');self.assertEqual(code,2,r);self.assertFalse(marker.exists())
        self.put('engine.py','def validate(x):\n    return x\ndef validate(x):\n    return False\n')
        code,r=self.call(out=self.base/'ambiguous');self.assertEqual(code,2,r);self.assertFalse(marker.exists())


    def test_setup_and_teardown_count_but_class_hooks_are_unassigned(self):
        self.put('test_flow.py','import unittest\nfrom engine import validate\nclass Tests(unittest.TestCase):\n    @classmethod\n    def setUpClass(cls):\n        validate(1)\n    @classmethod\n    def tearDownClass(cls):\n        validate(1)\n    def setUp(self):\n        validate(1)\n    def tearDown(self):\n        validate(1)\n    def test_green(self):\n        self.assertTrue(True)\n')
        code,r=self.call();self.assertEqual(code,0,r)
        self.assertEqual(r['unassigned_call_events'],2)
        self.assertEqual(self.result()['tests'][0]['call_events'],2)

    def test_other_thread_call_is_explicitly_out_of_scope(self):
        self.put('test_flow.py','import unittest,threading\nfrom engine import validate\nclass Tests(unittest.TestCase):\n    def test_thread(self):\n        t=threading.Thread(target=validate,args=(1,))\n        t.start();t.join()\n')
        code,r=self.call();self.assertEqual(code,1,r)
        self.assertEqual(r['status'],'NOT_OBSERVED_IN_SCOPE');self.assertEqual(r['observed_tests'],[])
        self.assertIn('Other threads/processes',' '.join(r['warnings']))

    def test_same_qualified_code_with_changed_constant_is_rejected(self):
        self.put('test_flow.py','import unittest,engine\ncode=engine.validate.__code__\nengine.validate.__code__=code.replace(co_consts=(None,100))\nclass Tests(unittest.TestCase):\n    def test_replaced(self):\n        engine.validate(1)\n')
        code,r=self.call();self.assertEqual(code,2,r)
        self.assertIn('CODE_MISMATCH',r['gaps']);self.assertEqual(r['observed_tests'],[])

    def test_duplicate_test_identity_refuses_execution(self):
        marker=self.base/'SHOULD_NOT_RUN'
        self.put('test_flow.py',f'import unittest\nfrom pathlib import Path\nclass Tests(unittest.TestCase):\n    def test_body(self):\n        Path({str(marker)!r}).touch()\ndef load_tests(loader,tests,pattern):\n    return unittest.TestSuite([Tests("test_body"),Tests("test_body")])\n')
        code,r=self.call();self.assertEqual(code,2,r)
        self.assertIn('DUPLICATE_TEST_ID',r['gaps']);self.assertFalse(marker.exists())

    def test_custom_runner_that_omits_tests_is_incomplete(self):
        self.put('test_flow.py','import unittest\nclass Tests(unittest.TestCase):\n    def test_body(self):\n        pass\n    def run(self,result=None):\n        return result\n')
        code,r=self.call();self.assertEqual(code,2,r)
        self.assertIn('TEST_EXECUTION_INCOMPLETE',r['gaps']);self.assertEqual(r['tests_run'],0)

    def test_descendant_process_does_not_outlive_worker(self):
        marker=self.base/'SHOULD_NOT_APPEAR'
        child=f'import time;from pathlib import Path;time.sleep(0.7);Path({str(marker)!r}).touch()'
        self.put('test_flow.py',f'import unittest,subprocess,sys\nfrom engine import validate\nclass Tests(unittest.TestCase):\n    def test_child(self):\n        subprocess.Popen([sys.executable,"-c",{child!r}])\n        validate(1)\n')
        code,r=self.call();self.assertEqual(code,0,r)
        import time
        time.sleep(0.9)
        self.assertFalse(marker.exists())

    def test_unexpected_success_and_fixture_error_are_explicit(self):
        self.put('test_flow.py','import unittest\nfrom engine import validate\nclass Tests(unittest.TestCase):\n    @unittest.expectedFailure\n    def test_xpass(self):\n        self.assertTrue(validate(1))\n    def test_error(self):\n        validate(1)\n        raise RuntimeError("synthetic")\n')
        code,r=self.call();self.assertEqual(code,1,r);self.assertEqual(r['status'],'OBSERVED_WITH_FAILURE')
        rows={t['id']:t['outcome'] for t in self.result()['tests']}
        self.assertEqual(rows['test_flow.Tests.test_xpass'],'XPASS')
        self.assertEqual(rows['test_flow.Tests.test_error'],'ERROR')

    def test_large_test_identifiers_keep_packet_bounded(self):
        self.put('test_flow.py','import unittest\nfrom engine import validate\nclass Tests(unittest.TestCase):\n    def id(self):\n        return super().id()+"x"*3000\n    def test_a(self):\n        validate(1)\n    def test_b(self):\n        validate(1)\n    def test_c(self):\n        validate(1)\n')
        code,r=self.call();self.assertEqual(code,0,r)
        self.assertTrue(r['test_details_omitted']);self.assertEqual(r['observed_test_count'],3)
        self.assertEqual(len(self.result()['tests']),3)


if __name__=='__main__':
    unittest.main(verbosity=2)
