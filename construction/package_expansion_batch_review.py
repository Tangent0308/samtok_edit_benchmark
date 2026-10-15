"""Package specified reviewed batches from an already validated increment."""
import argparse
import json
from pathlib import Path

from expand_reviewed_v2 import ROOT, sha, write
from samtok_benchmark.v2.review import package_review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--subset', type=Path, required=True)
    args = parser.parse_args()
    manifest = ROOT / 'release/benchmark/cases.jsonl'
    validation = json.loads(manifest.with_name('validation.json').read_text())
    if validation['manifest_sha256'] != sha(manifest):
        raise ValueError('Increment manifest has not finished validation')
    ledger = Path(__file__).with_name('expansion_reviews')
    ids = {r['source_id'] for name in args.batch
           for r in json.loads((ledger / (name + '.json')).read_text())
           if r['decision'] == 'accept'}
    cases = [c for c in map(json.loads, manifest.open())
             if c['source']['image_id'] in ids]
    if {c['source']['image_id'] for c in cases} != ids:
        raise ValueError('Requested batches are missing from the validated increment')
    for case in cases:
        decision = ROOT / 'decisions' / (case['source']['image_id'] + '.json')
        if case['instruction_review']['authoring_record_sha256'] != sha(decision):
            raise ValueError('A decision changed after the increment was built')
    if args.subset.exists() and any(args.subset.iterdir()):
        raise FileExistsError('Use a fresh subset directory')
    args.subset.mkdir(parents=True, exist_ok=True)
    subset_manifest = args.subset / 'cases.jsonl'
    subset_manifest.write_text(''.join(json.dumps(c, ensure_ascii=False) + '\n' for c in cases))
    required = {c['source']['image'] for c in cases} | {c['review']['card'] for c in cases}
    required |= {u['target']['mask'] for c in cases for u in c['units']}
    inventory = [r for r in map(json.loads, manifest.with_name('asset_manifest.jsonl').open())
                 if r['path'] in required]
    (args.subset / 'asset_manifest.jsonl').write_text(
        ''.join(json.dumps(r) + '\n' for r in inventory))
    write(args.subset / 'subset_provenance.json', {
        'batches': args.batch, 'parent_manifest_sha256': sha(manifest),
        'cases': len(cases), 'status': 'partial_expansion_review_only'})
    result = package_review(subset_manifest, ROOT / 'release', args.output)
    write(args.output / 'benchmark/subset_provenance.json',
          json.loads((args.subset / 'subset_provenance.json').read_text()))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
