"""Independent CLI tests on synthetic Python source; never import the fixtures."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
CLI = HERE/'impact.py'


class ImpactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base/'source'
        self.root.mkdir()
        self.out = self.base/'derived'
        self.put('engine.py', 'def validate(x):\n    return x > 0\n')
        self.put('pipeline.py', 'from engine import validate as check\ndef run(x):\n    return check(x)\n')
        self.put('test_flow.py', 'from pipeline import run as launch\ndef test_good():\n    assert launch(1)\n')

    def put(self, path, text):
        p = self.root/path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode())

    def trace(self, symbol='engine.validate', extra=(), root=None, out=None):
        p = subprocess.run([sys.executable, str(CLI), 'trace', '--root', str(root or self.root),
                            '--symbol', symbol, '--out', str(out or self.out), *map(str,extra)],
                           capture_output=True, timeout=35)
        self.assertTrue(p.stdout, p.stderr.decode())
        self.assertLessEqual(len(p.stdout), 8192)
        return p.returncode, json.loads(p.stdout)

    def graph(self):
        return json.loads((self.out/'graph.json').read_bytes())

    def verify(self, digest=None):
        p = subprocess.run([sys.executable, str(CLI), 'verify', '--root', str(self.root), '--out', str(self.out),
                            '--graph-sha256', digest or hashlib.sha256((self.out/'graph.json').read_bytes()).hexdigest()],
                           capture_output=True, timeout=35)
        self.assertTrue(p.stdout, p.stderr.decode())
        return p.returncode, json.loads(p.stdout)

    def test_alias_transitive_candidate_test_and_exact_edges(self):
        code, report = self.trace()
        self.assertEqual(code, 0, report)
        by_name = {c['symbol']:c for c in report['candidates']}
        self.assertEqual(by_name['pipeline.run']['distance'], 1)
        self.assertEqual(by_name['test_flow.test_good']['distance'], 2)
        self.assertTrue(by_name['test_flow.test_good']['candidate_test'])
        for edge in self.graph()['edges']:
            data = (self.root/edge['path']).read_bytes()
            self.assertEqual(data[edge['start']:edge['end']].decode(), edge['quote'])
            self.assertEqual(edge['source_sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(self.verify()[1]['mechanical'], 'PASS')
        self.assertEqual(report['analysis'], 'STATIC_PARTIAL')

    def test_unicode_crlf_offsets(self):
        self.put('pipeline.py', 'from engine import validate as check\r\ndef run(x):\r\n    café = "é"; return check(x)\r\n')
        code, r = self.trace()
        self.assertEqual(code, 0, r)
        edge = next(e for e in self.graph()['edges'] if e['caller']=='pipeline.run')
        data = (self.root/'pipeline.py').read_bytes()
        self.assertEqual(data[edge['start']:edge['end']], b'check')
        self.assertEqual(edge['line'], 3)
        self.assertEqual(self.verify()[1]['mechanical'], 'PASS')

    def test_parameter_assignment_and_duplicate_import_shadowing(self):
        self.put('shadow.py', 'from engine import validate as check\ndef a(check):\n    return check(1)\ndef b():\n    check = lambda x: x\n    return check(1)\n')
        self.put('rebound.py', 'from engine import validate as check\ncheck = lambda x: x\ndef wrong():\n    return check(1)\n')
        self.trace()
        edges = self.graph()['edges']
        self.assertFalse(any(e['caller'].startswith(('shadow.', 'rebound.')) for e in edges))
        self.assertTrue(any('SHADOW' in u['reason'] for u in self.graph()['unknowns']))

    def test_same_name_modules_are_not_conflated(self):
        self.put('other.py', 'def validate(x):\n    return False\ndef wrong(x):\n    return validate(x)\n')
        self.trace()
        self.assertNotIn('other.wrong', {c['symbol'] for c in self.graph()['candidates']})
        self.assertTrue(any(e['callee']=='other.validate' for e in self.graph()['edges']))

    def test_relative_module_alias_and_cycle_cutoff(self):
        self.put('pkg/__init__.py', '')
        self.put('pkg/core.py', 'def check(x):\n    return x\n')
        self.put('pkg/client.py', 'from .core import check as ok\ndef run():\n    return ok(1)\n')
        self.put('cycle.py', 'from engine import validate\ndef a():\n    validate(1); b()\ndef b():\n    return a()\n')
        _, report = self.trace('pkg.core.check')
        self.assertIn('pkg.client.run', {c['symbol'] for c in report['candidates']})
        _, cycle = self.trace(out=self.base/'cycle', extra=('--hops', 1))
        self.assertTrue(cycle['trace_truncated'])
        self.assertEqual(len({c['symbol'] for c in cycle['candidates']}), len(cycle['candidates']))

    def test_target_source_is_never_executed(self):
        marker = self.base/'PWNED'
        self.put('hostile.py', f'from pathlib import Path\nPath({str(marker)!r}).write_text("executed")\nraise RuntimeError("DO NOT IMPORT")\ndef unseen():\n    return 0\n')
        code, r = self.trace()
        self.assertEqual(code, 0, r)
        self.assertFalse(marker.exists())

    def test_syntax_dynamic_wildcard_and_nested_gaps(self):
        self.put('broken.py', 'def (: nope')
        self.put('dynamic.py', 'from engine import *\ndef hidden(obj):\n    def nested():\n        return validate(1)\n    return obj.method()\n')
        code, r = self.trace()
        self.assertEqual(code, 1, r)
        g = self.graph()
        self.assertTrue(g['gaps'])
        self.assertTrue(g['unknowns'])
        self.assertFalse(any(e['caller'].startswith('dynamic.') for e in g['edges']))

    def test_source_snapshot_and_graph_mutations(self):
        self.trace()
        expected = hashlib.sha256((self.out/'graph.json').read_bytes()).hexdigest()
        self.put('engine.py', 'def validate(x):\n    return False\n')
        self.assertEqual(self.verify(expected)[1]['mechanical'], 'FAIL')
        (self.out/'graph.json').write_bytes((self.out/'graph.json').read_bytes()+b' ')
        self.assertEqual(self.verify(expected)[1]['mechanical'], 'FAIL')

    def test_symlink_fifo_parent_traversal_and_output_preservation(self):
        (self.root/'escape.py').symlink_to('/etc/passwd')
        os.mkfifo(self.root/'pipe.py')
        code, report = self.trace()
        self.assertEqual(code, 1, report)
        before = (self.out/'graph.json').read_bytes()
        self.assertEqual(self.trace()[0], 2)
        self.assertEqual((self.out/'graph.json').read_bytes(), before)
        alias = self.base/'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        self.assertEqual(self.trace(root=str(alias/'..'/'source'), out=self.base/'bad')[0], 2)

    def test_caps_and_unknown_symbol_never_safe(self):
        for i, extra in enumerate([('--files',1), ('--file-bytes',4), ('--nodes',4), ('--seconds',0.000001)]):
            code, r = self.trace(out=self.base/f'cap-{i}', extra=extra)
            self.assertNotEqual(code, 0, r)
            self.assertNotEqual(r.get('mechanical'), 'PASS')
        code, r = self.trace('missing.target')
        self.assertEqual(code, 1)
        self.assertEqual(r['status'], 'UNKNOWN_SYMBOL')
        self.assertNotIn('safe_to_edit', r)

    def test_rebound_export_and_method_dispatch_remain_unknown(self):
        self.put('engine.py', 'def validate(x):\n    return x\nvalidate = lambda x: False\nclass C:\n    def method(self):\n        return 1\n')
        self.put('methods.py', 'import engine\ndef run():\n    return engine.C.method(None)\n')
        self.trace()
        self.assertFalse(any(e['callee']=='engine.validate' for e in self.graph()['edges']))
        self.assertFalse(any(e['callee']=='engine.C.method' for e in self.graph()['edges']))

    def test_conditional_wildcard_and_class_test_callers(self):
        self.put('uncertain.py', 'from engine import validate\nif True:\n    from other import *\ndef run():\n    return validate(1)\n')
        self.put('test_class.py', 'from pipeline import run as launch\nclass Tests:\n    def test_good(self):\n        assert launch(1)\n')
        _,r=self.trace()
        self.assertFalse(any(e['caller']=='uncertain.run' for e in self.graph()['edges']))
        candidate=next(c for c in r['candidates'] if c['symbol']=='test_class.Tests.test_good')
        self.assertTrue(candidate['candidate_test'])

    def test_exception_and_pattern_binding_shadowing(self):
        self.put('binding.py', 'from engine import validate as check\ndef a():\n    try:\n        raise ValueError()\n    except ValueError as check:\n        return check(1)\ndef b(x):\n    match x:\n        case {"value": check}:\n            return check(1)\n')
        self.trace()
        self.assertFalse(any(e['caller'].startswith('binding.') for e in self.graph()['edges']))

    def test_duplicate_module_and_parser_refusal_are_explicit(self):
        self.put('same.py', 'def choose():\n    return 1\n')
        self.put('same/__init__.py', 'def choose():\n    return 2\n')
        self.put('deep.py', 'data = ' + '['*1000 + '0' + ']'*1000)
        code,r=self.trace()
        self.assertEqual(code,1,r)
        self.assertGreaterEqual(r['gap_count'],3)
        self.assertFalse(any(d['id']=='same.choose' for d in self.graph()['definitions']))

    def test_verify_failure_packet_is_bounded(self):
        folder='/'.join(['a'*150,'b'*150,'c'*150])
        names=[f'{folder}/source_{i:02}.py' for i in range(24)]
        for name in names:
            self.put(name,'def spare():\n    return 0\n')
        self.trace()
        expected=hashlib.sha256((self.out/'graph.json').read_bytes()).hexdigest()
        for name in names:
            (self.root/name).unlink()
        p=subprocess.run([sys.executable,str(CLI),'verify','--root',str(self.root),'--out',str(self.out),'--graph-sha256',expected],capture_output=True,timeout=35)
        self.assertEqual(p.returncode,2)
        self.assertLessEqual(len(p.stdout),8192)
        self.assertEqual(json.loads(p.stdout)['mechanical'],'FAIL')


if __name__ == '__main__':
    unittest.main(verbosity=2)
