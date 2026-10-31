import json, re, sys, collections, os
import numpy as np
from PIL import Image
from concurrent.futures import ProcessPoolExecutor

ROOT = '/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2'
MAN = '/opt/tiger/tanyue/samtok_edit_benchmark/data/v2_1084/cases.jsonl'
cases = [json.loads(l) for l in open(MAN)]

PERSON = set('person persons man men woman women boy girl boys girls dancer dancers officer officers child children kid kids people player players worker workers vendor vendors performer performers rider riders cyclist runner runners guard guards soldier soldiers pedestrian pedestrians lady gentleman figure student students musician musicians singer spectator spectators tourist tourists shopper customer customers driver passenger monk nun priest athlete athletes skier surfer swimmer baby toddler policeman policewoman bride groom couple crowd fan fans member members drummer guitarist chef waiter seller merchant farmer fisherman cook teenager adult elderly individual hiker climber'.split())
GARMENT = set('shirt t-shirt tshirt jacket coat top trousers pants jeans shorts skirt dress sleeve sleeves cap hat helmet scarf headscarf vest sock socks shoe shoes boot boots glove gloves hoodie sweater jersey uniform costume outfit suit blouse apron backpack bag handbag belt tie collar hood strap glasses sunglasses mask headband turban veil robe cape cardigan kimono sari tunic overalls leggings sandal sandals sneaker sneakers bandana hair beard face hand hands arm arms leg legs head watch necklace bracelet earring wristband armband badge lanyard umbrella cloak shawl gown pullover parka blazer bodysuit tank polo trunks swimsuit bikini'.split())
CLOTH_PAYLOAD = set('shirt t-shirt jacket coat top trousers pants jeans shorts skirt dress uniform costume outfit suit blouse hoodie sweater jersey vest robe gown clothes clothing attire'.split())
COLORS = ['red','blue','green','yellow','orange','purple','pink','black','white','gray','grey','brown','navy','teal','beige','tan','gold','golden','silver','maroon','burgundy','cream','ivory','violet','turquoise','cyan','magenta','olive','khaki','lavender','lilac','mint','coral','charcoal','bronze','copper','amber','crimson','scarlet','indigo','emerald','mustard','peach','rust','sky','dark','light','pale','bright','deep','glossy','matte','metallic','wooden','wood','metal','plastic','leather','striped','plaid','polka','dotted','checked','checkered','floral','camouflage','chrome','steel','brass','glass','denim','canvas','stone','marble','concrete','fabric','rubber','new','clean','plain','solid','shiny','dull','small','large','big','colored','coloured','sage','rose','royal','forest','lime','neon','hot','pastel','off-white','dark-blue','light-blue','wine','plum','jade','aqua','sand','sandy','champagne']
COLORSET = set(COLORS)
ZH_COLOR = {'red':['红'],'blue':['蓝'],'green':['绿'],'yellow':['黄'],'orange':['橙','橘'],'purple':['紫'],'pink':['粉'],'black':['黑'],'white':['白'],'gray':['灰'],'grey':['灰'],'brown':['棕','褐','咖啡'],'navy':['藏蓝','海军蓝','深蓝'],'teal':['青','蓝绿','水鸭'],'beige':['米','杏'],'gold':['金'],'golden':['金'],'silver':['银'],'maroon':['栗','褐红','酒红','暗红'],'burgundy':['酒红','勃艮第'],'cream':['奶油','米'],'ivory':['象牙'],'violet':['紫'],'turquoise':['绿松','青'],'cyan':['青'],'magenta':['品红','洋红'],'olive':['橄榄'],'khaki':['卡其'],'lavender':['薰衣草','淡紫'],'lilac':['淡紫','丁香'],'mint':['薄荷'],'coral':['珊瑚'],'charcoal':['炭','深灰'],'bronze':['青铜','古铜'],'copper':['铜'],'amber':['琥珀'],'crimson':['深红','绯红'],'scarlet':['猩红','鲜红'],'indigo':['靛'],'emerald':['祖母绿','翠绿'],'mustard':['芥末'],'peach':['桃'],'rust':['锈'],'tan':['棕褐','黄褐','浅棕','褐','驼']}
NUM_ZH = {'two':['两','二','2'],'three':['三','3'],'four':['四','4'],'five':['五','5'],'six':['六','6']}
OP_ZH = {'replace':['替换','换成','换为'],'remove':['移除','去掉','删除','移走','去除'],'add':['加','添加','增加','装','挂','贴','缝','放'],'attribute':['改为','改成','染','变为','换成','变成']}
LOC_WORDS = r'\b(left|right|top|bottom|upper|lower|front|back|center|centre|middle|nearest|farthest|foreground|background|leftmost|rightmost|topmost|first|second|third|fourth|fifth|behind|beside|next to|near|above|below|under|corner)\b'

def head_noun(phrase):
    p = phrase.lower()
    p = re.split(r'\b(of|on|at|in|near|behind|beside|with|by|from|under|above|below|to|that|which|between|along|across|over|carrying|holding|wearing|facing|closest|nearest|beneath|underneath|inside|around|against|held|worn|hanging|seated|sitting|standing|leaning|parked|immediately|just|left|right)\b', p)[0]
    w = re.findall(r"[a-z\-']+", p)
    w = [x for x in w if x not in ('the','a','an','selected')]
    return w[-1] if w else ''

def words(s): return re.findall(r"[A-Za-z\-']+", s.lower())

DS = 4
def label_ds(m):
    h, w = m.shape
    mm = m[:h - h % DS, :w - w % DS].reshape(h // DS, DS, w // DS, DS).any(axis=(1, 3))
    H_, W_ = mm.shape
    seen = np.zeros_like(mm, dtype=bool)
    comps = []
    ys, xs = np.where(mm)
    for y0, x0 in zip(ys.tolist(), xs.tolist()):
        if seen[y0, x0]: continue
        stack = [(y0, x0)]; seen[y0, x0] = True; n = 0; sy = 0; sx = 0
        while stack:
            y, x = stack.pop(); n += 1; sy += y; sx += x
            for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
                yy, xx = y + dy, x + dx
                if 0 <= yy < H_ and 0 <= xx < W_ and mm[yy, xx] and not seen[yy, xx]:
                    seen[yy, xx] = True; stack.append((yy, xx))
        comps.append((n, sy / n, sx / n))
    return comps

def mask_stats(args):
    cid, units, size = args
    W, H = size
    out = {}
    arrs = {}
    for u in units:
        p = os.path.join(ROOT, u['target']['mask'])
        try:
            m = np.array(Image.open(p).convert('L')) > 127
        except Exception as e:
            out[u['id']] = {'error': str(e)}; continue
        arrs[u['id']] = m
        r = {'shape': [m.shape[1], m.shape[0]], 'area': int(m.sum())}
        if m.any():
            ys, xs = np.where(m)
            r['bbox'] = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
            px, py = u['target']['point']
            r['point_in'] = bool(0 <= py < m.shape[0] and 0 <= px < m.shape[1] and m[py, px])
            # components via downsample label
            if True:
                comps = label_ds(m)
                tot = sum(cc[0] for cc in comps)
                big = [cc for cc in comps if cc[0] >= 0.05 * tot]
                cents = [(cc[1]*DS, cc[2]*DS) for cc in big]
                maxd = 0
                for i in range(len(cents)):
                    for j in range(i + 1, len(cents)):
                        d = ((cents[i][0] - cents[j][0]) ** 2 + (cents[i][1] - cents[j][1]) ** 2) ** .5
                        maxd = max(maxd, d)
                r['big_comp'] = len(big); r['max_comp_dist_frac'] = maxd / max(W, H)
        out[u['id']] = r
    pair = []
    ids = list(arrs)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = arrs[ids[i]], arrs[ids[j]]
            if a.shape != b.shape: continue
            inter = int((a & b).sum())
            if inter == 0: continue
            uni = int((a | b).sum())
            pair.append({'a': ids[i], 'b': ids[j], 'inter': inter, 'iou': inter / uni, 'frac_a': inter / max(1, a.sum()), 'frac_b': inter / max(1, b.sum())})
    # bbox containment
    return cid, out, pair

def main():
    jobs = [(c['id'], c['units'], c['source']['size']) for c in cases]
    with ProcessPoolExecutor(24) as ex:
        res = {cid: (o, p) for cid, o, p in ex.map(mask_stats, jobs, chunksize=8)}
    flags = []
    def F(c, u, check, sev, msg, **kw):
        d = {'case_id': c['id'], 'unit_id': u['id'] if u else None, 'check': check, 'auto_severity': sev, 'msg': msg}
        if u:
            d['instruction_ref'] = u['instruction_ref']; d['instruction_noref'] = u['instruction_noref']
        d.update(kw); flags.append(d)

    alltexts = collections.Counter()
    for c in cases:
        for u in c['units']:
            alltexts[u['instruction_ref'].lower()] += 1

    for ci, c in enumerate(cases):
        W, H = c['source']['size']
        mst, pairs = res[c['id']]
        parents = collections.defaultdict(list)
        for u in c['units']:
            s = u['instruction_spec']; t = u['target']; op = u['operation']
            ref = s['ref']; scope = s['scope']; R = u['instruction_ref']; N = u['instruction_noref']
            payload = s['payload'] or ''
            parents[t['physical_parent_zh']].append(u['id'])
            hn = head_noun(ref); sn = head_noun(scope)
            cat = (t['category'] or '').lower()
            refw = set(words(ref)); scopew = set(words(scope))
            is_person = (hn in PERSON) or (sn in PERSON) or cat in ('person', 'man', 'woman', 'dancer', 'people')
            has_garment = bool((refw | scopew | set(words(s.get('target_part') or ''))) & GARMENT)
            # 1 person/clothing
            if is_person and not has_garment:
                if op == 'attribute':
                    F(c, u, 'person_level_attribute', 'blocking', f'attribute applied to whole person (ref head={hn}, scope={scope})')
                elif op == 'replace':
                    pw = set(words(payload))
                    if pw & CLOTH_PAYLOAD:
                        F(c, u, 'person_replaced_by_clothing', 'blocking', f'person target replaced by clothing payload "{payload}"')
                    else:
                        F(c, u, 'person_replace', 'major', f'replace on whole person -> "{payload}"')
                elif op == 'remove':
                    F(c, u, 'person_remove', 'info', 'whole person removal (check scope)')
                elif op == 'add':
                    F(c, u, 'person_add_anchor', 'info', f'add with person anchor: {payload}')
            # 2 spatial
            bx = t['box']; cx = (bx[0] + bx[2]) / 2 / W; cy = (bx[1] + bx[3]) / 2 / H
            rl = ref.lower()
            # Strip relational clauses: only consider position words that attach to ref directly (not after 'of the X' for part relation is OK since part inside parent)
            rel_block = re.search(r'\b(left of|right of|behind|beside|next to|in front of|above|below|under|near the (?!center|centre|middle|lower|upper|left|right|top|bottom|front)|from the|closest to|nearest to|across|between)\b', rl)
            def has(p): return re.search(p, rl) is not None
            contra = []
            if has(r'\b(far left|leftmost|far-left)\b') and cx > 0.5: contra.append('far-left but cx=%.2f' % cx)
            elif has(r'\b(at|on|in) the (upper |lower |middle |front |back )?left\b|\bleft side\b|\bon the left\b|\bat left\b|\bto the left\b|\bupper left\b|\blower left\b|\bleft (foreground|background)\b') and cx > 0.6 and not has(r'left of'): contra.append('left but cx=%.2f' % cx)
            if has(r'\b(far right|rightmost|far-right)\b') and cx < 0.5: contra.append('far-right but cx=%.2f' % cx)
            elif has(r'\b(at|on|in) the (upper |lower |middle |front |back )?right\b|\bright side\b|\bon the right\b|\bat right\b|\bupper right\b|\blower right\b|\bright (foreground|background)\b') and cx < 0.4 and not has(r'right of'): contra.append('right but cx=%.2f' % cx)
            if has(r'\b(at the top|upper|topmost|top left|top right|at top)\b') and cy > 0.6 and not has(r'upper (body|arm|part|half|edge|floor|deck|level|section|portion|window|story|storey|shelf)'): contra.append('upper/top but cy=%.2f' % cy)
            if has(r'\b(at the bottom|lower left|lower right|lower center|bottommost|bottom left|bottom right|at bottom|near the bottom|near the lower)\b') and cy < 0.4: contra.append('lower/bottom but cy=%.2f' % cy)
            if has(r'\bnear the (center|centre|middle)\b|\bat the (center|centre)\b|\bin the (center|centre)\b') and (abs(cx - 0.5) > 0.3 or abs(cy - 0.5) > 0.35): contra.append('center but cx=%.2f cy=%.2f' % (cx, cy))
            if contra:
                F(c, u, 'spatial_contradiction', 'blocking' if not rel_block else 'major', '; '.join(contra), box=bx, size=[W, H], relational=bool(rel_block))
            # 3 ref/noref equivalence
            exp = None
            if ref and ref in R:
                exp = R.replace(ref, 'the selected ' + scope, 1)
            else:
                F(c, u, 'ref_not_in_instruction', 'minor', f'spec.ref "{ref}" not substring of instruction_ref')
            if exp is not None and exp.strip() != N.strip():
                F(c, u, 'noref_mismatch', 'major', f'expected noref "{exp}"')
            nl = N.lower()
            m = re.search(r'the selected [\w\- ]+ of the selected', nl)
            if m: F(c, u, 'noref_double_selected', 'minor', m.group(0))
            m = re.search(r'\b(\w+) of the (selected )?\1\b', nl)
            if m: F(c, u, 'dup_noun', 'minor', m.group(0))
            rest = N.replace('the selected ' + scope, '') if ('the selected ' + scope) in N else N
            locs = re.findall(r'\b(left|right|leftmost|rightmost|foreground|background|center|front row|back row|nearest|farthest)\b', rest.lower())
            if locs: F(c, u, 'noref_location_leak', 'minor', f'noref has location words {locs}')
            if 'the selected' not in nl: F(c, u, 'noref_no_selected', 'major', 'noref lacks "the selected"')
            # payload/attr consistency
            if payload and payload.lower() not in R.lower(): F(c, u, 'payload_not_in_ref', 'major', f'payload "{payload}" not in ref instruction')
            if payload and payload.lower() not in N.lower(): F(c, u, 'payload_not_in_noref', 'major', f'payload "{payload}" not in noref instruction')
            # 4 operation semantics
            if op == 'replace':
                pw = [w for w in words(payload) if w not in ('a', 'an', 'one', 'the', 'pair', 'of', 'set', 'with')]
                ph = head_noun(payload)
                same = ph and (ph == sn or ph == hn or ph == cat or ph.rstrip('s') == sn.rstrip('s') or (cat and ph in cat.split()))
                mods = [w for w in pw if w != ph]
                if same and all(w in COLORSET for w in mods):
                    F(c, u, 'replace_is_recolor', 'major', f'replace payload "{payload}" only changes color/material of same category "{scope}"')
                if not payload: F(c, u, 'replace_no_payload', 'blocking', 'replace with empty payload')
            if op == 'attribute':
                if not s['attributes'] or not all(a.get('value') for a in s['attributes']):
                    if not re.search(r'\b(tint|make)\b', R.lower()): F(c, u, 'attribute_no_value', 'major', 'attribute without property/value')
                # value equals current color mentioned in ref
                for a in s['attributes']:
                    v = (a.get('value') or '').lower()
                    if v and a.get('property') == 'color' and re.search(r'\b' + re.escape(v) + r'\b', ref.lower()):
                        F(c, u, 'attribute_noop', 'major', f'target color value "{v}" already in ref "{ref}"')
            if op == 'remove':
                if s['remove_mode'] != 'whole' and not re.search(r'\bfrom\b|\bshort|\bsleeveless|\bcut\b|\btrim', R.lower()):
                    F(c, u, 'remove_scope_missing', 'major', f'remove_mode={s["remove_mode"]} target_part={s["target_part"]} but no scope phrase')
                if s['remove_mode'] == 'whole' and re.search(r'\b(handle|strap|sleeve|lid|cap|wheel|brim|collar|hood|logo|leg|arm|door|window)s? of\b', ref.lower()):
                    pass
            if op == 'add':
                pl = s['placement'] or {}
                if not pl.get('relation'): F(c, u, 'add_no_relation', 'major', 'add without placement.relation')
                if pl.get('anchor_mode') not in (None, 'support'): F(c, u, 'add_nonsupport_anchor', 'major', f'anchor_mode={pl.get("anchor_mode")}')
                if re.search(r'\b(its|it|their)\b', payload.lower()) or re.search(r'\b(its|their)\b', R.lower()):
                    F(c, u, 'add_dangling_its', 'minor', f'dangling its/their in add: "{R}"')
                fw = words(payload)[:1]
                if fw and fw[0] not in ('a', 'an', 'one', 'two', 'three', 'four', 'five', 'six', 'some', 'pair', 'single') and not re.match(r'\d', payload):
                    F(c, u, 'add_no_quantity', 'minor', f'add payload without explicit count: "{payload}"')
                # anchor from instruction: "on/to ... <ref>" ensure ref appears after relation
                if ref and ref not in R: F(c, u, 'add_anchor_not_ref', 'major', 'anchor text differs from ref')
                if re.search(r'\b(near|beside|next to|above|below|under)\b', (pl.get('relation') or '')):
                    F(c, u, 'add_reference_relation', 'major', f'relation={pl.get("relation")}')

            # --- extra semantic checks ---
            pw_all = words(payload)
            if op == 'replace' and payload:
                nouns = [w for w in pw_all if w not in COLORSET and w not in ('a','an','one','the','and','with')]
                if not nouns:
                    F(c, u, 'replace_bare_color', 'blocking', f'replace payload has no object noun: "{payload}"')
            if op == 'attribute':
                for a in s['attributes']:
                    v = (a.get('value') or '').lower(); vw = words(v)
                    if a.get('property') == 'color':
                        if set(vw) & (GARMENT | CLOTH_PAYLOAD) or vw[:1] in (['a'], ['an']):
                            F(c, u, 'attribute_value_is_object', 'blocking', f'color value is an object phrase: "{v}"')
                        elif vw and all(w in ('dark', 'light', 'pale', 'bright', 'deep') for w in vw):
                            F(c, u, 'attribute_value_vague', 'major', f'color value has no hue: "{v}"')
            WORN = set('shirt t-shirt jacket coat top trousers pants jeans shorts skirt dress vest sweater hoodie jersey costume blouse uniform outfit sweatshirt cardigan tunic robe'.split())
            if op == 'remove' and s['remove_mode'] == 'whole' and (sn in WORN or hn in WORN):
                F(c, u, 'remove_worn_garment', 'major', f'removing worn garment "{scope}" leaves undefined body/underlayer')
            if op == 'add':
                if sn in PERSON or hn in PERSON or cat in ('person',):
                    F(c, u, 'add_on_whole_person', 'major', f'add anchor is a whole person ("{ref}") with no attachment site')
                if re.search(r'\b(glow|light|lighting|shadow|reflection|shine)\b', payload.lower()) and not re.search(r'lights\b|lamp|light (bulb|fixture)', payload.lower()):
                    F(c, u, 'add_nonobject_payload', 'major', f'add payload is not an object: "{payload}"')
                GEN = ('a small logo','a small badge','a small sign','a small label','a small arrow','a white stripe','a small symbol','a small emblem','a small sticker','a small plaque','a small flag','a small flower','a small bird','a cushion','a small decal','a red symbol','a white emblem','a blue logo','a small bead')
                if payload.lower().strip() in GEN:
                    F(c, u, 'add_generic_payload', 'minor', f'generic/underspecified add payload "{payload}"')
            if op == 'remove' and t['geometry']['area_fraction'] > 0.15:
                F(c, u, 'remove_huge_region', 'major', f'remove of {t["geometry"]["area_fraction"]:.2f} of image ("{ref}") is ill-posed inpainting')
            if op in ('replace','attribute','remove') and cat in ('building','wall','sky','road','ground','street','sidewalk') and op=='remove':
                F(c, u, 'remove_structural', 'major', f'remove structural element "{cat}"')
            # 5 mask geometry
            ms = mst.get(u['id'], {})
            if 'error' in ms: F(c, u, 'mask_unreadable', 'blocking', ms['error']); continue
            if ms['shape'] != [W, H]: F(c, u, 'mask_size_mismatch', 'blocking', f'{ms["shape"]} vs {[W, H]}')
            af = ms['area'] / (W * H)
            if ms['area'] == 0: F(c, u, 'mask_empty', 'blocking', 'empty mask'); continue
            if af < 0.0002: F(c, u, 'mask_tiny', 'major', f'area_frac={af:.5f} ({ms["area"]} px)')
            if ms['bbox'] != list(bx): F(c, u, 'box_mismatch', 'major', f'mask bbox {ms["bbox"]} vs box {bx}')
            if not ms['point_in']: F(c, u, 'point_outside', 'major', f'point {t["point"]} not in mask')
            part_level = bool(s.get('target_part')) or (hn != sn and sn in GARMENT) or sn in ('sleeve', 'handle', 'strap', 'lid', 'collar', 'brim', 'wheel', 'cuff', 'pocket', 'button', 'logo', 'rim')
            if af > 0.4: F(c, u, 'mask_huge', 'major' if part_level else 'minor', f'area_frac={af:.3f}', part_level=part_level)
            elif af > 0.25 and op != 'add': F(c, u, 'mask_large', 'info', f'area_frac={af:.3f}')
            if ms.get('big_comp', 1) >= 2 and ms.get('max_comp_dist_frac', 0) > 0.35:
                F(c, u, 'mask_far_fragments', 'major', f'{ms["big_comp"]} big components, max dist {ms["max_comp_dist_frac"]:.2f} of image')
            # box touching edges and huge? (skip)
            # 6 text quality
            for name, txt in (('ref', R), ('noref', N)):
                if re.search(r'\b(\w+) \1\b', txt.lower()) and not re.search(r'\b(that that|had had)\b', txt.lower()): F(c, u, 'repeated_word', 'minor', f'{name}: {txt}')
                if '  ' in txt: F(c, u, 'double_space', 'minor', f'{name}')
                if not txt.strip().endswith('.'): F(c, u, 'no_period', 'minor', f'{name}: {txt}')
                if re.search(r'[^\x00-\x7f’“”‘—–é°×]', txt): F(c, u, 'odd_char', 'minor', f'{name}: {txt}')
                m1 = re.search(r'\ba ([aeiou]\w+)', txt)
                if m1 and not re.search(r'\ba (one|uni|use|usb|eu|u[a-z]?[aeiou])', txt.lower()): F(c, u, 'article_a_an', 'minor', name + ': ' + m1.group(0))
                m2 = re.search(r'\ban ([bcdfgjklmnpqrstvwxyz]\w+)', txt)
                if m2 and not re.search(r'\ban (hour|honest|heir|LED|SUV|MRI|NBA|FBI|x|r|s|f|l|m|n)', txt): F(c, u, 'article_a_an', 'minor', name + ': ' + m2.group(0))
            nw = len(R.split()); nnw = len(N.split())
            if nw > 26: F(c, u, 'ref_too_long', 'minor', f'{nw} words')
            if nnw > 16: F(c, u, 'noref_too_long', 'minor', f'{nnw} words')
            if re.search(r'\b(which|located|the one)\b', R.lower()): F(c, u, 'style_clause', 'minor', R)
            # chinese consistency
            Z = u['instruction_ref_zh']; ZN = u['instruction_noref_zh']
            for txtE, txtZ, nm in ((R, Z, 'ref'), (N, ZN, 'noref')):
                ew = words(txtE.replace(ref, '') if nm == 'ref' else txtE)
                for col, zz in ZH_COLOR.items():
                    if col in words(payload) or any(col == a.get('value', '').lower().split()[-1:] and False for a in s['attributes']):
                        if not any(z in txtZ for z in zz): F(c, u, 'zh_color_missing', 'minor', f'{nm}: payload color "{col}" not in zh "{txtZ}"')
                for a in s['attributes']:
                    for col in words(a.get('value', '')):
                        if col in ZH_COLOR and not any(z in txtZ for z in ZH_COLOR[col]): F(c, u, 'zh_color_missing', 'minor', f'{nm}: attr color "{col}" not in zh "{txtZ}"')
                for n_en, nz in NUM_ZH.items():
                    if n_en in words(payload) and not any(z in txtZ for z in nz): F(c, u, 'zh_count_missing', 'minor', f'{nm}: count "{n_en}" not in zh "{txtZ}"')
                if not any(k in txtZ for k in OP_ZH[op]): F(c, u, 'zh_op_mismatch', 'minor', f'{nm}: op {op} not reflected in zh "{txtZ}"')
            if '选中' not in ZN: F(c, u, 'zh_noref_no_selected', 'minor', ZN)
            if re.search(r'(左|右)', u['instruction_ref_zh']) and not re.search(r'\b(left|right|leftmost|rightmost)\b', R.lower()):
                F(c, u, 'zh_side_extra', 'minor', f'zh has 左/右 but en has none: {u["instruction_ref_zh"]}')
            if re.search(r'\bleft\b|\bleftmost\b', R.lower()) and '右' in Z and '左' not in Z: F(c, u, 'zh_side_flip', 'major', f'en left vs zh: {Z}')
            if re.search(r'\bright\b|\brightmost\b', R.lower()) and '左' in Z and '右' not in Z: F(c, u, 'zh_side_flip', 'major', f'en right vs zh: {Z}')
            if alltexts[R.lower()] > 1: F(c, u, 'duplicate_instruction_global', 'info', f'appears {alltexts[R.lower()]}x in manifest')
            # completion requirement/edit contract consistency
            if u['edit_contract'].get('definition') and u['edit_contract']['definition'] != R: F(c, u, 'contract_definition_mismatch', 'minor', u['edit_contract']['definition'])
            if not u['completion_requirement'].startswith(R): F(c, u, 'completion_mismatch', 'minor', u['completion_requirement'][:120])
            if op == 'add' and u['edit_contract'].get('locator_semantics') != 'addition_support': F(c, u, 'add_contract', 'major', u['edit_contract'].get('locator_semantics'))
            if u['interaction']['has_ref'] is False and u['interaction']['locator'] == 'none': F(c, u, 'noref_no_locator', 'blocking', 'noref without locator')
        # 7 parents
        for p, ids in parents.items():
            if len(ids) > 1: F(c, None, 'same_physical_parent', 'major', f'parent "{p}" used by {ids}')
        pids = collections.Counter(u['target']['parent_instance_id'] for u in c['units'])
        for p, n in pids.items():
            if n > 1: F(c, None, 'same_parent_instance_id', 'major', f'{p} x{n}')
        refs = collections.Counter(u['instruction_ref'] for u in c['units'])
        for r_, n in refs.items():
            if n > 1: F(c, None, 'duplicate_instruction_in_case', 'major', r_)
        for pr in pairs:
            if pr['iou'] > 0.3 or pr['frac_a'] > 0.5 or pr['frac_b'] > 0.5:
                F(c, None, 'mask_overlap', 'blocking', f'{pr["a"]}/{pr["b"]} iou={pr["iou"]:.2f} fa={pr["frac_a"]:.2f} fb={pr["frac_b"]:.2f}')
            elif pr['frac_a'] > 0.05 or pr['frac_b'] > 0.05:
                F(c, None, 'mask_overlap_small', 'minor', f'{pr["a"]}/{pr["b"]} iou={pr["iou"]:.2f} fa={pr["frac_a"]:.2f} fb={pr["frac_b"]:.2f}')
        # box containment between units
        us = c['units']
        for i in range(len(us)):
            for j in range(len(us)):
                if i == j: continue
                a, b = us[i]['target']['box'], us[j]['target']['box']
                if a[0] >= b[0] and a[1] >= b[1] and a[2] <= b[2] and a[3] <= b[3]:
                    aa = (a[2] - a[0]) * (a[3] - a[1]); bb = (b[2] - b[0]) * (b[3] - b[1])
                    F(c, None, 'box_contained', 'info', f'{us[i]["id"]} box inside {us[j]["id"]} box (area ratio {aa / bb:.2f})')
        # same-category spatial ordering
        for i in range(len(us)):
            for j in range(i + 1, len(us)):
                ri, rj = us[i]['instruction_spec']['ref'].lower(), us[j]['instruction_spec']['ref'].lower()
                ci_ = (us[i]['target']['box'][0] + us[i]['target']['box'][2]) / 2; cj_ = (us[j]['target']['box'][0] + us[j]['target']['box'][2]) / 2
                if head_noun(ri) == head_noun(rj) and head_noun(ri):
                    li = re.search(r'\bleft\b', ri) and not re.search(r'\bright\b', ri); lj = re.search(r'\bleft\b', rj) and not re.search(r'\bright\b', rj)
                    rri = re.search(r'\bright\b', ri) and not re.search(r'\bleft\b', ri); rrj = re.search(r'\bright\b', rj) and not re.search(r'\bleft\b', rj)
                    if (li and rrj and ci_ > cj_) or (rri and lj and ci_ < cj_):
                        F(c, None, 'relative_lr_contradiction', 'blocking', f'{us[i]["id"]}("{ri}") cx={ci_:.0f} vs {us[j]["id"]}("{rj}") cx={cj_:.0f}')
    # templated batch marker
    out = {'n_cases': len(cases), 'n_units': sum(len(c['units']) for c in cases), 'flags': flags,
           'mask_stats': {cid: res[cid][0] for cid in res}}
    cnt = collections.Counter(f['check'] for f in flags)
    out['counts'] = dict(cnt.most_common())
    json.dump(out, open('/tmp/samtok_audit/auto_checks.json', 'w'), ensure_ascii=False, indent=1)
    for k, v in cnt.most_common(): print(v, k)
    print('cases flagged (non-info):', len({f['case_id'] for f in flags if f['auto_severity'] != 'info'}))

if __name__ == '__main__':
    main()
