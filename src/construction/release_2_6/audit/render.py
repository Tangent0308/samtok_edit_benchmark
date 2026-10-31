import json, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from concurrent.futures import ProcessPoolExecutor

ROOT = '/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2'
MAN = '/opt/tiger/tanyue/samtok_edit_benchmark/data/provenance/construction_inputs/base1084/cases.jsonl'
OUT = '/tmp/samtok_audit/views'
COL = {'U1': (255, 40, 40), 'U2': (40, 120, 255), 'U3': (255, 200, 0), 'U4': (220, 0, 255), 'U5': (0, 220, 80)}
try:
    FONT = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 28)
    FONTS = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 20)
except Exception:
    FONT = FONTS = ImageFont.load_default()


def outline(mask_img, size, thick):
    m = mask_img.resize(size, Image.NEAREST)
    dil = m.filter(ImageFilter.MaxFilter(thick * 2 + 1))
    ero = m.filter(ImageFilter.MinFilter(3))
    a = np.array(dil) > 127
    b = np.array(ero) > 127
    return a & ~b


def render(c):
    src = Image.open(os.path.join(ROOT, c['source']['image'])).convert('RGB')
    W, H = src.size
    TW = 1600
    s = TW / W
    th = int(H * s)
    if th > 1300:
        s = 1300 / H; th = 1300; TW = int(W * s)
    full = src.resize((TW, th), Image.BILINEAR)
    fa = np.array(full)
    masks = {}
    for u in c['units']:
        m = Image.open(os.path.join(ROOT, u['target']['mask'])).convert('L')
        masks[u['id']] = m
        e = outline(m, (TW, th), 2)
        fa[e] = COL[u['id']]
    full = Image.fromarray(fa)
    d = ImageDraw.Draw(full)
    for u in c['units']:
        x1, y1, x2, y2 = [v * s for v in u['target']['box']]
        d.rectangle([x1, y1, x2, y2], outline=COL[u['id']], width=1)
        px, py = [v * s for v in u['target']['point']]
        d.ellipse([px - 5, py - 5, px + 5, py + 5], fill=COL[u['id']], outline=(0, 0, 0))
        lx, ly = max(0, x1), max(0, y1 - 30)
        d.rectangle([lx, ly, lx + 50, ly + 30], fill=(0, 0, 0))
        d.text((lx + 4, ly), u['id'], fill=COL[u['id']], font=FONT)
    # crops
    n = len(c['units'])
    CW = TW // n if n > 3 else TW // 3
    CW = min(CW, 540)
    crops = []
    for u in c['units']:
        x1, y1, x2, y2 = u['target']['box']
        bw, bh = x2 - x1, y2 - y1
        pad = max(bw, bh) * 0.35 + 20
        cx1, cy1 = max(0, int(x1 - pad)), max(0, int(y1 - pad))
        cx2, cy2 = min(W, int(x2 + pad)), min(H, int(y2 + pad))
        cr = src.crop((cx1, cy1, cx2, cy2))
        mc = masks[u['id']].crop((cx1, cy1, cx2, cy2))
        sc = min(CW / cr.width, CW / cr.height)
        sz = (max(1, int(cr.width * sc)), max(1, int(cr.height * sc)))
        cr = cr.resize(sz, Image.BILINEAR)
        ca = np.array(cr)
        e = outline(mc, sz, 1)
        ca[e] = COL[u['id']]
        cr = Image.fromarray(ca)
        dd = ImageDraw.Draw(cr)
        dd.rectangle([0, 0, 60, 26], fill=(0, 0, 0))
        dd.text((3, 1), u['id'], fill=COL[u['id']], font=FONTS)
        crops.append(cr)
    ch = max(cr.height for cr in crops)
    canvas = Image.new('RGB', (max(TW, CW * min(n, 5)), th + ch + 6), (30, 30, 30))
    canvas.paste(full, (0, 0))
    x = 0
    for cr in crops:
        canvas.paste(cr, (x, th + 6)); x += CW
    canvas.save(os.path.join(OUT, c['id'] + '.jpg'), quality=85)
    return c['id']


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    cases = [json.loads(l) for l in open(MAN)]
    if len(sys.argv) > 1:
        ids = set(sys.argv[1:]); cases = [c for c in cases if c['id'] in ids]
    with ProcessPoolExecutor(24) as ex:
        for i, r in enumerate(ex.map(render, cases, chunksize=4)):
            pass
    print('done', len(cases))
