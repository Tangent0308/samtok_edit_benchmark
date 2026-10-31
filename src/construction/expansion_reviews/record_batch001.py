"""Replay frozen direct visual decisions without blessing changed assets."""
import argparse
import json
from pathlib import Path
from samtok_benchmark.paths import construction_metadata
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from expand_reviewed_v2 import ROOT, sha, write


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--all',action='store_true',help='Verify/replay every frozen batch')
    args=parser.parse_args()
    paths=sorted((construction_metadata() / 'expansion_reviews').glob('batch*.json')) if args.all else [construction_metadata() / 'expansion_reviews/batch001.json']
    records=[record for path in paths for record in json.loads(path.read_text())]
    if len({r['source_id'] for r in records})!=len(records):
        raise ValueError('Duplicate source across frozen batches')
    by_source={r['source_id']:r for r in records}
    for path in sorted((construction_metadata() / 'expansion_reviews/revisions').glob('*.json')):
        revision=json.loads(path.read_text());sid=revision['source_id']
        if sid not in by_source:continue
        if by_source[sid]!=revision['previous_record']:
            raise ValueError(f'Revision history mismatch: {path}')
        by_source[sid]=revision['record']
    records=list(by_source.values())
    for record in records:
        source_id = record['source_id']
        candidate = ROOT / 'candidates' / source_id
        if sha(candidate / record.get('review_card_name','candidate.jpg')) != record['review_card_sha256']:
            raise ValueError(f'Reviewed card changed: {source_id}')
        if record['decision'] == 'accept':
            source = json.loads((candidate / 'source.json').read_text())
            if sha(source['image_path']) != record['source_sha256']:
                raise ValueError(f'Reviewed source changed: {source_id}')
        for card in record.get('additional_review_cards', []):
            if sha(card['path']) != card['sha256']:
                raise ValueError(f'Additional review card changed: {source_id}')
        path = ROOT / 'decisions' / f'{source_id}.json'
        if path.exists():
            if json.loads(path.read_text()) != record:
                raise ValueError(f'Existing decision differs: {path}')
        else:
            write(path, record)
    print(f'Verified/replayed {len(records)} frozen direct visual decisions.')


if __name__ == '__main__':
    main()
