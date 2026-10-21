"""Generate synthetic engineering sources and run the single invocation once."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from test_onecall import fixture

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work', type=Path, required=True)
    args = p.parse_args()
    args.work.mkdir()
    root = args.work / 'input'
    root.mkdir()
    (root / '01-plan.md').write_text('# Sample release\nDay 1: ship blue is approved; GO.\n')
    (root / '02-review.txt').write_bytes('Owner café.\r\nDay 2 supersedes Day 1: ship blue is STOP; dependency validation failed.\r\n'.encode())
    (root / 'readiness.pdf').write_bytes(fixture.pdf(['Initial readiness.', 'ship blue requires a dependency re-test before rollout.']))
    before = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(root.iterdir())}
    command = [sys.executable, str(HERE/'onecall.py'), 'evidence', '--root', str(root), '--query', 'ship blue', '--out', str(args.work/'derived')]
    run = subprocess.run(command, capture_output=True, timeout=35)
    packet = json.loads(run.stdout)
    assert run.returncode == 0 and packet['mechanical'] == 'PASS', packet
    assert len(run.stdout) < 8192
    assert before == {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(root.iterdir())}
    # Actually execute the previous CLI route for the same selected spans.
    lens_cli = HERE.parent/'sentinel-lens-0'/'lens.py'
    baseline = args.work/'baseline'
    baseline_calls = 0
    def old(*arguments):
        nonlocal baseline_calls
        baseline_calls += 1
        r = subprocess.run([sys.executable, str(lens_cli), *map(str, arguments)], capture_output=True, timeout=35)
        assert r.returncode == 0, r.stdout
        return json.loads(r.stdout)
    snapshot = old('snapshot', '--root', root, '--out', baseline)
    quoted = []
    for q in packet['citations']:
        quoted.append(old('quote', '--manifest', baseline/'manifest.json', '--manifest-sha256', snapshot['manifest_sha256'],
                          '--chunk', q['chunk'], '--start', q['start'], '--end', q['end']))
        assert all(q[key] == value for key, value in quoted[-1].items())
    citations_path = args.work/'baseline-citations.json'
    citations_path.write_text(json.dumps(quoted))
    checked = old('verify', '--manifest', baseline/'manifest.json', '--manifest-sha256', snapshot['manifest_sha256'],
                  '--root', root, '--citations', citations_path)
    assert checked['mechanical'] == packet['mechanical'] == 'PASS'
    report = dict(command_shape='python onecall.py evidence --root INPUT --query "ship blue" --out NEW_DERIVED',
                  cli_invocations=1, baseline_cli_invocations=baseline_calls, baseline_citations=len(quoted),
                  baseline_quote_and_mechanical_results_equal=True, manual_offset_calculations=0,
                  baseline_method='Actual snapshot + quote per selected span + verify; selected offsets supplied from the onecall packet.',
                  packet_bytes=len(run.stdout), original_bytes_unchanged=True, source_hashes=before, packet=packet)
    (args.work/'receipt.json').write_text(json.dumps(report, indent=2, ensure_ascii=True)+'\n')
    (args.work/'brief.md').write_text('# Synthetic release decision\n\n'
        'Question: can the blue release start?\n\n'
        '**STOP.** The Day 2 review supersedes the Day 1 GO. The physical PDF page 2 '
        'requires a dependency re-test. These are the demo author’s semantic findings; '
        'ONECALL returns literal citations, not this conclusion.\n\n'
        'The generated packet contains all three source-linked excerpts and their exact '
        'UTF-8 byte ranges. They mechanically PASS, including the outdated GO passage. '
        'The semantic-review warning is retained. Original source bytes are unchanged.\n\n'
        '[Actual packet](derived/packet.json) · [full manifest](derived/manifest.json)\n')
    print(json.dumps(report, indent=2, ensure_ascii=True))


if __name__ == '__main__':
    main()
