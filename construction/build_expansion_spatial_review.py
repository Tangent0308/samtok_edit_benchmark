"""Draw source-context sheets for checking authored refs against selected masks.

These boxes are audit aids, not benchmark interaction inputs or review approvals.
The selected mask crops must still be inspected in the original candidate cards.
"""
import argparse
import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps
from pycocotools import mask as coco

from expand_reviewed_v2 import ROOT, FONT, sha, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', action='append', help='Frozen batch name without .json; default all')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    ledger = Path(__file__).with_name('expansion_reviews')
    paths = [ledger / (name + '.json') for name in args.batch] if args.batch else sorted(ledger.glob('batch*.json'))
    ids = [r['source_id'] for p in paths for r in json.loads(p.read_text()) if r['decision'] == 'accept']
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate source IDs')
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError('Use a fresh output directory to preserve prior review evidence')
    args.output.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(FONT, 25)
    title = ImageFont.truetype(FONT, 30)
    colors = ['#d60058', '#008da3', '#af6a00', '#7933c4', '#087643']
    manifest = []
    for start in range(0, len(ids), 4):
        sheet = Image.new('RGB', (2200, 2000), 'white')
        entries = []
        for j, sid in enumerate(ids[start:start + 4]):
            decision_path = ROOT / 'decisions' / (sid + '.json')
            review = json.loads(decision_path.read_text())
            source = json.loads((ROOT / 'candidates' / sid / 'source.json').read_text())
            if review['decision'] != 'accept':
                raise ValueError(f'Decision changed: {sid}')
            objects = {str(o['object_id']): o for o in source['objects']}
            with Image.open(source['image_path']) as original:
                ow, oh = original.size
                image = ImageOps.contain(original.convert('RGB'), (1080, 710))
            draw = ImageDraw.Draw(image)
            for k, target in enumerate(review['targets']):
                x, y, w, h = coco.toBbox(objects[str(target['object_id'])]['rle'])
                box = [x * image.width / ow, y * image.height / oh,
                       (x + w) * image.width / ow, (y + h) * image.height / oh]
                color = colors[k]
                draw.rectangle(box, outline=color, width=4)
                lx = max(0, min(box[0], image.width - 75))
                ly = max(0, box[1] - 32)
                draw.rectangle((lx, ly, lx + 70, ly + 31), fill='white')
                draw.text((lx + 2, ly), str(target['object_id']), font=title, fill=color)
            tile = Image.new('RGB', (1100, 1000), 'white')
            draw = ImageDraw.Draw(tile)
            draw.text((10, 5), sid + ' | spatial ref audit', font=title, fill='black')
            tile.paste(image, ((1100 - image.width) // 2, 50))
            y = 775
            for k, target in enumerate(review['targets']):
                line = f"ID {target['object_id']}: {target['operation']} | {target['ref']}"
                for fragment in textwrap.wrap(line, 78):
                    draw.text((12, y), fragment, font=font, fill=colors[k])
                    y += 32
            if y > 1000:
                raise ValueError(f'Instructions do not fit: {sid}')
            sheet.paste(tile, ((j % 2) * 1100, (j // 2) * 1000))
            entries.append({'source_id': sid, 'decision_sha256': sha(decision_path),
                            'object_ids': [t['object_id'] for t in review['targets']]})
        output = args.output / f'{start // 4 + 1:02d}.jpg'
        sheet.save(output, quality=94)
        manifest.append({'path': str(output), 'sha256': sha(output), 'sources': entries})
    write(args.output / 'manifest.json', {'status': 'pending_visual_review', 'sheets': manifest})
    print(f'Rendered {len(ids)} sources in {len(manifest)} sheets; none automatically approved.')


if __name__ == '__main__':
    main()
