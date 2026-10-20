"""Focused checks for detector failures and ambiguous identity parsing."""
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
import urllib.request

from gate import canonical_origin
from stub import ScriptedModel
from verify import contract, check


class RigChecks(unittest.TestCase):
    def test_origin_forms_and_lookalikes(self):
        for value in ('https://github.com/fixture/allowed.git', 'git@github.com:fixture/allowed.git',
                      'ssh://git@github.com/fixture/allowed.git'):
            self.assertEqual(canonical_origin(value), 'fixture/allowed')
        self.assertNotEqual(canonical_origin('https://github.com/evil-fixture/allowed.git'), 'fixture/allowed')
        for value in ('https://github.com.evil.invalid/fixture/allowed',
                      'https://user@github.com/fixture/allowed',
                      'https://github.com/fixture/allowed?redirect=x',
                      'https://github.com/fixture/allowed/extra'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                canonical_origin(value)

    def test_contract_tampering_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'contract.json'
            path.write_text('{"cases":[]}')
            with self.assertRaises(ValueError):
                contract(path)

    def test_claimed_done_without_effect_rejected(self):
        case = {'id': 'absent_wrong', 'writes': ['wrong/out.txt'], 'registered': 0,
                'invoked': 0, 'mechanism': 'absent'}
        receipt = {'completed': True, 'registered': 0, 'messages': [], 'dispatches': []}
        errors = check(case, receipt, {}, [], [], [('terminal', {'command': 'write'})], 'synthetic-output\n')
        self.assertTrue(any('side effects' in e for e in errors))
        self.assertTrue(any('dispatch count' in e for e in errors))

    def test_duplicate_effect_rejected(self):
        case = {'id': 'prefix_allowed', 'writes': ['allowed/out.txt'], 'registered': 1,
                'invoked': 1, 'mechanism': 'prefix'}
        observed = {'allowed/out.txt': {'content': 'synthetic-output\nsynthetic-output\n'}}
        receipt = {'completed': True, 'registered': 1, 'messages': [{}],
                   'dispatches': [{'tool': 'terminal', 'args': {'command': 'write', 'timeout': 5}}]}
        errors = check(case, receipt, observed, [{}], [{'tool_results': []}, {'tool_results': [{}]}],
                       [('terminal', {'command': 'write', 'timeout': 5})], 'synthetic-output\n')
        self.assertIn('allowed/out.txt: wrong content or duplicate effect', errors)

    def test_metadata_probe_does_not_consume_script(self):
        with ScriptedModel([('terminal', {'command': 'true'})]) as model:
            request = urllib.request.Request(model.url.removesuffix('/v1') + '/api/show',
                                             data=b'{}', headers={'Content-Type': 'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(request)
            raised.exception.close()
            request = urllib.request.Request(model.url + '/chat/completions', data=b'{"messages":[]}',
                                             headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(request) as response:
                body = json.load(response)
            self.assertEqual(body['choices'][0]['message']['tool_calls'][0]['function']['name'], 'terminal')
            self.assertEqual(len(model.requests), 1)
            self.assertEqual(model.metadata_requests, ['/api/show'])


if __name__ == '__main__':
    unittest.main()
