import json, glob, collections, re
A = '/tmp/samtok_audit'
OUT = '/opt/tiger/tanyue/samtok_edit_benchmark/docs/BENCHMARK_AUDIT_20261015_ZH.md'
cases = [json.loads(l) for l in open('/opt/tiger/tanyue/samtok_edit_benchmark/data/provenance/construction_inputs/base1084/cases.jsonl')]
order = {c['id']: i for i, c in enumerate(cases)}
byid = {c['id']: c for c in cases}
F = [json.loads(l) for l in open(A + '/findings.jsonl')]
R = json.load(open(A + '/reviewed_meta.json'))
auto = json.load(open(A + '/auto_checks.json'))
prec = json.load(open(A + '/autoflag_precision.json'))
sample = set(json.load(open(A + '/unflagged_sample.json')))
trans = {}
for f in glob.glob(A + '/trans/out_*.json'):
    try: trans.update(json.load(open(f)))
    except Exception as e: print('trans load fail', f, e)
SEV = {'blocking': 0, 'major': 1, 'minor': 2}
SEVZH = {'blocking': '阻断', 'major': '严重', 'minor': '轻微'}
CATZH = {
    'person_clothing_level': '人物/服装层级错误', 'category_mismatch': '指代类别与 mask 不符', 'wrong_instance_spatial': '方位/序数/实例指代错误',
    'ambiguous_ref': '指代歧义', 'mask_quality': 'mask 质量', 'replace_is_attribute': 'replace 实为属性修改', 'ill_posed_edit': '编辑不合理/不可执行',
    'add_anchor': 'add 锚点不当', 'attribute_value': '属性值问题（无变化/含糊）', 'independence_violation': '多单元同一物理对象/相互冲突',
    'ref_noref_mismatch': 'Ref/No-ref 不等价', 'translation': '中文翻译不一致', 'grammar_style': '措辞/文法/描述细节'}
# attach translations
for i, o in enumerate(F):
    k = f"{o['case_id']}|{o.get('unit_id')}|{i}"
    t = trans.get(k)
    o['evidence_zh'] = t.get('evidence_zh') if t else None
    o['other_zh'] = t.get('other_zh') if t else None
    o['_i'] = i

def esc(s):
    if s is None: return ''
    return str(s).replace('|', '\\|').replace('\n', ' ').strip()

def worst(l):
    return min((SEV[o['severity']] for o in l), default=9)

vis = [o for o in F if o.get('verified_visually')]
txt = [o for o in F if not o.get('verified_visually')]
bycase = collections.defaultdict(list); byunit = collections.defaultdict(list)
for o in vis:
    bycase[o['case_id']].append(o)
    if o.get('unit_id'): byunit[(o['case_id'], o['unit_id'])].append(o)
txt_case = collections.defaultdict(list)
for o in txt: txt_case[o['case_id']].append(o)
flagged = set()
for f in auto['flags']:
    if f['auto_severity'] == 'info' and f['check'] not in ('box_contained', 'person_remove', 'person_add_anchor'): continue
    flagged.add(f['case_id'])
unf = [c['id'] for c in cases if c['id'] not in flagged]
n_units = sum(len(c['units']) for c in cases)

def rng(cid):
    i = order[cid]
    if i < 200: return 'A'
    if i < 869: return 'B'
    if i < 945: return 'C'
    return 'D'
RNGZH = {'A': '原版 #0–#199（200 case）', 'B': '扩充 #200–#868（669 case）', 'C': '扩充 #869–#944（76 case）', 'D': '扩充尾段 #945–#1083（139 case）'}

L = []
P = L.append
P('# SAMTok Benchmark v2（1,084 case）指令与标注全量审查报告')
P('')
P('审查日期：2026-10-15。审查对象：`data/provenance/construction_inputs/base1084/cases.jsonl`（1,084 case / 3,872 个编辑单元 U1–U5），数据根 `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2/`。本次审查**未修改** manifest 或任何已有数据文件；全部中间产物在 `/tmp/samtok_audit/`。')
P('')
P('> 重要说明：本次“目视审查”由 assistant（主审）与其分派的 28 个并行视觉审查子代理完成，属于**模型目视复核**，不是独立人工验收。主审本人另外抽查了 10 个 case 用于校准（与子代理结论 10/10 一致）。所有结论均附具体证据，可在 `/tmp/samtok_audit/views/<case_id>.jpg` 复核。')
P('')
# ---------------- summary
cases_bl = sorted([c for c, l in bycase.items() if worst(l) == 0], key=lambda c: order[c])
cases_mj = sorted([c for c, l in bycase.items() if worst(l) == 1], key=lambda c: order[c])
cases_mn = sorted([c for c, l in bycase.items() if worst(l) == 2], key=lambda c: order[c])
units_bl = [u for u, l in byunit.items() if worst(l) == 0]
units_mj = [u for u, l in byunit.items() if worst(l) == 1]
units_mn = [u for u, l in byunit.items() if worst(l) == 2]
txt_only_cases = sorted(set(txt_case) - set(bycase), key=lambda c: order[c])
txt_units = set((o['case_id'], o['unit_id']) for o in txt)
P('## 0. 结论摘要')
P('')
P(f'- **全部 1,084 个 case 均已打开合成审图（原图 + 各 U 的 mask 轮廓/box/point + 局部放大）逐一目视复核**；3,872 个单元全部经过自动规则检查。')
P(f'- 经目视确认存在问题的 case：**{len(bycase)} / 1,084（{len(bycase)/1084:.1%}）**；其中最严重级别为阻断（blocking）的 **{len(cases_bl)}** 个、严重（major）**{len(cases_mj)}** 个、仅轻微（minor）**{len(cases_mn)}** 个。另有 {len(txt_only_cases)} 个 case 仅有自动文本规则发现的轻微措辞问题。')
P(f'- 按单元计：目视确认问题单元 **{len(byunit)} / {n_units}（{len(byunit)/n_units:.1%}）**，其中阻断 **{len(units_bl)}**、严重 **{len(units_mj)}**、轻微 **{len(units_mn)}**；文本规则另记 {len(txt)} 条轻微问题（涉及 {len(txt_units)} 个单元，部分与目视问题重叠）。')
P('- **问题高度集中在扩充集尾段**：manifest #945–#1083（139 case）几乎全部由模板化指令构成（“the X at the left / near the center”，94% 的 ref 是此模板），其中 ' + f"{sum(1 for c in bycase if rng(c)=='D' and worst(bycase[c])==0)} 个 case 有阻断问题、{sum(1 for c in bycase if rng(c)=='D' and worst(bycase[c])<=1)} 个有严重及以上问题。#869–#944 的 76 个 case 也明显退化（{sum(1 for c in bycase if rng(c)=='C' and worst(bycase[c])==0)} 个阻断）。已知问题 `v2-sa_9357354`、`v2-sa_9345888` 只是这一批系统性缺陷的两个例子。")
P('- 最主要问题类别：①replace 实为换色/换材质/换图案（应归 attribute）；②指代歧义（同类实例多、ref 不能唯一确定）；③方位词/序数与 mask 实际位置矛盾；④对“整个人”改色或把人替换成衣服（人物/服装层级错误）；⑤ref 名词与 mask 实际物体不符（如 “officer” 实为衬衫、“bottle” 实为水母）。')
P(f'- 未被任何自动规则命中的 628 个 case 全部目视复核后，仍有 **{sum(1 for c in unf if worst(bycase.get(c,[]))==0)}（{sum(1 for c in unf if worst(bycase.get(c,[]))==0)/len(unf):.1%}）** 个含阻断问题、**{sum(1 for c in unf if worst(bycase.get(c,[]))<=1)}（{sum(1 for c in unf if worst(bycase.get(c,[]))<=1)/len(unf):.1%}）** 个含严重及以上问题——说明现有规则只能抓住模板化的显性错误，细粒度指代/歧义问题必须靠视觉复核。')
P('- 建议：正式评测前**排除全部阻断 case**，并将 #869–#1083 尾段整体退回重新撰写/复核；其余严重问题按第 4 节清单逐条修订后重新跑构建校验与目视复核。')
P('')
# ---------------- method
P('## 1. 审查范围与方法')
P('')
P('### 1.1 阶段 A：全量自动检查（3,872 单元）')
P('')
P('脚本 `/tmp/samtok_audit/phaseA.py`，完整输出 `/tmp/samtok_audit/auto_checks.json`（含每单元 mask 统计与全部 flag）。检查项：')
P('')
P('1. 人物/服装层级：ref 头名词或 scope 为人物词（person/man/woman/dancer/officer/child/player/worker/vendor… 约 80 个）且未提及服装/部件时的 attribute/replace/remove/add；人物被替换为服装 payload；add 锚点为整个人。')
P('2. 方位一致性：ref 中 left/right/top/bottom/upper/lower/center/far left/leftmost 等与 box 中心（相对图宽高）的矛盾（如 left 但 cx>0.6W、center 但偏离中心>0.3W）；同 case 同类名词 left/right 的相对次序矛盾。关系短语（left of / behind 等）降级为 major。')
P('3. Ref/No-ref 等价：No-ref 是否严格等于把 `spec.ref` 替换为 `the selected <scope>`；payload 是否出现在两种指令中；No-ref 是否泄露方位词、是否出现 “the selected X of the selected Y”、“handle of the handle” 类重复。')
P('4. 操作语义：replace payload 与原物同类且只差颜色/材质/图案修饰词；replace payload 无名词（“with blue”）；attribute 缺值、值无色相（“to dark”）、值为物体短语、值与 ref 中现有颜色相同；remove 范围（contents/hem/part）是否写明；移除穿着中的服装、移除建筑/大面积区域；add 是否有 relation、是否 support 锚点、payload 是否有悬空 its、是否笼统（a small logo）、是否非实物（glow）。')
P('5. mask/几何：mask 可读、尺寸一致、空/极小、mask 外接框与 stored box 一致、point 是否在 mask 内、同 case 两 mask IoU>0.3 或包含>50%、box 包含关系、部件级指令 mask>40% 图像、远距离多碎块。')
P('6. 文本质量：重复词、双空格、句末标点、a/an、异常字符、长度（Ref>26 词、No-ref>16 词）、`which/located/the one` 从句；中文与英文的颜色、数量、操作动词、左右方位一致性。')
P('7. 独立性与重复：同 case `physical_parent_zh`/`parent_instance_id`/annotation_id/mask 哈希重复；同 case 及全库重复指令。')
P('')
P('结构性检查全部通过：No-ref 与 Ref 的模板等价（0 例不一致）、mask 尺寸/外接框/point 位置、同 case mask 显著重叠均 0 例。这说明问题主要是**语义层面**的，现有构建校验（结构/哈希）无法发现。')
P('')
P('自动规则命中情况（命中单元数 / 被目视确认 / 被目视否定；其余为未明确表态）：')
P('')
P('| 规则 | 命中 | 确认 | 否定 | 说明 |')
P('|---|---:|---:|---:|---|')
NOTE = {'add_dangling_its': '文本问题，约定由主审集中记录（全部计为轻微文本问题），子代理“否定”仅表示未重复记录',
        'add_generic_payload': '同上；笼统 payload 记为轻微', 'box_contained': '仅提示信息，多数 mask 本身不重叠', 'zh_op_mismatch': '“剪去/系”等译法正确，规则误报',
        'noref_location_leak': '多为安装部位 site（如 upper-right corner），非定位泄露', 'remove_scope_missing': '“including its contents/to make it knee-length”已写明范围，规则误报',
        'spatial_contradiction': '约 30% 为相对群组/父物体的合理描述', 'mask_far_fragments': '多为被遮挡物体的合法分离可见块'}
for chk, n, c, r in prec:
    P(f'| `{chk}` | {n} | {c} | {r} | {NOTE.get(chk, "")} |')
P('')
P('### 1.2 阶段 B：目视复核')
P('')
P(f'- 为每个 case 渲染合成审图 `/tmp/samtok_audit/views/<case_id>.jpg`（原图缩放至 ~1600px，U1 红/U2 蓝/U3 金/U4 紫/U5 绿 mask 轮廓 + box + point，下方为每个 U 的放大裁剪），渲染脚本 `/tmp/samtok_audit/render.py`。必要时子代理另开原图/原 mask 局部核对颜色、文字、号码。')
P(f'- **第一轮**：阶段 A 命中的全部 **{len(flagged)}** 个 case（排除纯 info 规则）+ 在未命中 case 中**按 manifest 顺序等间隔抽取的 {len(sample)} 个**对照样本，共 {len(flagged)+len(sample)} 个，分 16 批由并行子代理逐 case 目视，逐条确认/否定自动 flag 并记录新问题。')
P(f'- **第二轮**：剩余 {1084-len(flagged)-len(sample)} 个未命中 case 全部目视（12 批）。因此**全部 1,084 case 均被目视**；残余错误率既可用第一轮随机样本估计，也可用全部 628 个未命中 case 的普查值。')
P('- 主审抽查：主审本人打开 10 个 case（含 9357354、9345888、7810159、6823812、1093348、6534458、6859686、8043384、8364417、9681021）核对子代理结论，10/10 一致（记录 `/tmp/samtok_audit/lead_spotcheck.jsonl`）。')
P('- 每条问题记录：case、unit、严重度、类别、具体证据（指令所说 vs 图像/mask 实际，含坐标）、具体修改建议（重写后的 ref/no-ref 或 mask/spec/操作修改）、是否目视核验。')
P('- 严重度：**阻断**=该单元错误/不可评分（错实例、层级错误、ref 与 mask 位置或类别矛盾、无对象的 replace、无变化的编辑、两单元同一物体）；**严重**=有歧义或可能误导模型/评审（ref 可指多个实例、replace 实为换色、移除穿着衣物/整栋建筑、mask 含明显邻居或漏大块）；**轻微**=措辞、颜色词、翻译等不改变目标的问题。')
P('')
P('### 1.3 未覆盖/局限（如实说明）')
P('')
P('- 目视复核由模型完成，不等同独立人工验收；子代理之间的严重度尺度可能有轻微差异（主审抽查一致，但样本仅 10 个）。“指代歧义”“replace 是否算真实结构变化”等判断存在主观边界。')
P('- 合成审图为缩放图；极细小目标（<0.05% 图像）、轻微 mask 边缘误差、遮挡后的少量漏标未系统检查；未逐像素比对 mask 与原 RLE（构建校验已做）。')
P('- 未检查：模型实际可编辑性/生成结果（尚无模型输出）、训练集泄露与近重复、difficulty 标签准确性、completion_requirement/preserve 文本的逐字正确性（仅检查与 instruction 一致）、中文翻译的全部细节（只做规则检查 + 目视中顺带发现）。')
P('- 未发现问题 ≠ 无问题：未命中且目视未记录问题的 case 仍可能存在细小歧义。')
P('')
# ---------------- stats
P('## 2. 总体统计')
P('')
P('### 2.1 按严重度（目视确认）')
P('')
P('| 级别 | case 数（按最严重问题计） | 单元数（按最严重问题计） | 问题条数 |')
P('|---|---:|---:|---:|')
cnt = collections.Counter(o['severity'] for o in vis)
P(f'| 阻断 | {len(cases_bl)} | {len(units_bl)} | {cnt["blocking"]} |')
P(f'| 严重 | {len(cases_mj)} | {len(units_mj)} | {cnt["major"]} |')
P(f'| 轻微 | {len(cases_mn)} | {len(units_mn)} | {cnt["minor"]} |')
P(f'| 合计 | {len(bycase)} | {len(byunit)} | {len(vis)} |')
P('')
P(f'另有自动文本规则发现、未单独目视判定的轻微问题 {len(txt)} 条（add 指令悬空 its {sum(1 for o in txt if o["source"].endswith("its"))} 条、笼统 add payload {sum(1 for o in txt if o["source"].endswith("payload"))} 条），见 4.4 节。')
P('')
P('### 2.2 按类别 × 严重度（目视确认问题条数）')
P('')
P('| 类别 | 阻断 | 严重 | 轻微 | 合计 | 涉及 case |')
P('|---|---:|---:|---:|---:|---:|')
cc = collections.defaultdict(collections.Counter); ccase = collections.defaultdict(set)
for o in vis:
    cc[o['category']][o['severity']] += 1; ccase[o['category']].add(o['case_id'])
for cat in sorted(cc, key=lambda k: -sum(cc[k].values())):
    x = cc[cat]
    P(f'| {CATZH.get(cat, cat)} (`{cat}`) | {x["blocking"]} | {x["major"]} | {x["minor"]} | {sum(x.values())} | {len(ccase[cat])} |')
P('')
P('### 2.3 按 manifest 区段')
P('')
P('| 区段 | case 数 | 有阻断 | 严重及以上 | 任意问题 | 阻断率 |')
P('|---|---:|---:|---:|---:|---:|')
for r in 'ABCD':
    rc = [c['id'] for c in cases if rng(c['id']) == r]
    b = sum(1 for c in rc if worst(bycase.get(c, [])) == 0); m = sum(1 for c in rc if worst(bycase.get(c, [])) <= 1); a = sum(1 for c in rc if c in bycase)
    P(f'| {RNGZH[r]} | {len(rc)} | {b} | {m} | {a} | {b/len(rc):.1%} |')
P('')
P('尾段 #945–#1083 的特征：`instruction_review.version=2.5.0-draft`、`instruction_design` 无 recipe；`difficulty.evidence_zh` 多为“X、Y、Z 和 W 是四个不同对象”，`specific_protection_zh` 为“保留……”泛化句；ref 94% 为 “the <noun> at/near the <方位>” 模板，方位词与实际位置大量矛盾，attribute 常直接对人改色，replace 常为“同类换色”或“人→衣服”“X→裸颜色”。这与 README 中“每张图具有 assistant 直接视觉审核依据”的表述不符。')
P('')
P('### 2.4 残余错误率（自动规则未命中部分）')
P('')
sv = [c for c in sample]
def rate(lst, k):
    n = sum(1 for c in lst if worst(bycase.get(c, [])) <= k); return n, n / len(lst)
su = [(c, u['id']) for c in sv for u in byid[c]['units']]
uu = [(c, u['id']) for c in unf for u in byid[c]['units']]
def urate(lst, k):
    n = sum(1 for x in lst if worst(byunit.get(x, [])) <= k); return n, n / len(lst)
P('| 口径 | 样本 | case 含阻断 | case 含严重及以上 | case 含任意问题 | 单元含阻断 | 单元含严重及以上 |')
P('|---|---:|---:|---:|---:|---:|---:|')
for name, lst, ul in [(f'第一轮等间隔系统抽样（{len(sv)} case / {len(su)} 单元）', sv, su), (f'全部未命中 case 普查（{len(unf)} case / {len(uu)} 单元）', unf, uu)]:
    b = rate(lst, 0); m = rate(lst, 1); a = rate(lst, 2); ub = urate(ul, 0); um = urate(ul, 1)
    P(f'| {name} | {len(lst)} | {b[0]} ({b[1]:.1%}) | {m[0]} ({m[1]:.1%}) | {a[0]} ({a[1]:.1%}) | {ub[0]} ({ub[1]:.1%}) | {um[0]} ({um[1]:.1%}) |')
fb = rate(sorted(flagged), 0); fm = rate(sorted(flagged), 1)
P(f'| 对照：自动命中 case（{len(flagged)}） | {len(flagged)} | {fb[0]} ({fb[1]:.1%}) | {fm[0]} ({fm[1]:.1%}) | {rate(sorted(flagged),2)[0]} | | |')
P('')
p_ = rate(sv, 0)[1]; n_ = len(sv); se = (p_ * (1 - p_) / n_) ** .5
p2 = rate(sv, 1)[1]; se2 = (p2 * (1 - p2) / n_) ** .5
P(f'按等间隔抽样样本估计（近似随机样本处理），自动规则漏掉的 case 中约 {p_:.1%}（95% 区间约 ±{1.96*se:.1%}）含阻断问题、约 {p2:.1%}（±{1.96*se2:.1%}）含严重及以上问题；全量普查值（{rate(unf,0)[1]:.1%} / {rate(unf,1)[1]:.1%}）与之相符。未命中部分的主要问题是 replace 实为换色、同类实例歧义、同一人身上取多个单元、颜色词/类别词与图像不符等细粒度问题。')
P('')
# ---------------- categories
P('## 3. 问题类别说明与示例')
P('')
CATDESC = {
 'person_clothing_level': '对整个人做 attribute（“Change the color of the person to blue”）、把人 replace 成服装（“Replace the officer with a black uniform”），或指令说“衬衫”但 mask 是整个人。违反协议“不得把给人改色含糊代指衣服”“新旧对应同一层级”。集中在尾段模板 case；而且相当多此类单元的 mask 其实只是衣服（`category=person` 是错标），需同时修 ref 与 scope。',
 'wrong_instance_spatial': 'ref 的 left/right/center/upper/nearest/序数/号码/身体左右与 mask 实际位置不符，导致 ref-only 输入指向别的实例，并污染 completion_requirement/edit_contract。',
 'category_mismatch': 'ref 名词与 mask 实际物体不同类（“officer”实为白衬衫、“bottle”实为水母、“sign”实为灯、“belfry”实为方尖碑），或颜色/属性描述与原图明显不符导致指向错误。',
 'ambiguous_ref': '图中有多个同类实例都符合 ref（“the banner at the left”有两面并排横幅；“the shuttered window”有 40 扇），ref-only 或评审无法唯一确定目标。',
 'replace_is_attribute': 'replace 的新物与原物同类、只改颜色/材质/图案/文字（“Replace the boat with a blue boat”“puffer jacket → leather jacket”），或干脆是裸颜色/与原物相同（“with black”、红色敞篷车→红色敞篷车）。协议要求“单纯换色归 attribute”。',
 'ill_posed_edit': '编辑本身不合理或不可评分：移除穿在身上的衬衫/外套、移除整栋建筑/桥/屋顶、移除载人的婴儿车/轮椅、给已戴头盔者“加头盔”、给植物“加花盆”、加“a warm glow”等。',
 'attribute_value': '目标属性值与现状相同或几乎相同（白车改白、黑灯改 matte black），或值无色相（“to dark”），无法判断是否完成。',
 'mask_quality': 'mask 覆盖了错误/多余对象（整个人而非衬衫、两个人、气球+毯子当婴儿车、桥栏当桥），或只覆盖目标的一小部分、碎片化严重。',
 'independence_violation': '同一 case 两个单元落在同一物理对象（同一人的帽子和包、衬衫和袖子），或编辑相互冲突（U3 删除的人手里拿着 U2 要替换的镰刀）。违反“每图 2–5 个不同实物”。',
 'add_anchor': 'add 锚点不合适：锚点是整个人且无部位、座椅被人占据无可见座面、屋顶在画外等。',
 'translation': '中文与英文不一致（操作范围、颜色、方位不同）或中文错乱。',
 'grammar_style': '措辞/描述细节错误但目标仍可识别（颜色词偏差、手机写成相机、T 恤写成衬衫等）。',
 'ref_noref_mismatch': 'No-ref 的 scope 与 Ref 层级不同（“the selected lantern” vs ref 只指灯头）。'}
ex_by = collections.defaultdict(list)
for o in sorted(vis, key=lambda o: (SEV[o['severity']], order[o['case_id']])):
    ex_by[o['category']].append(o)
for ci, cat in enumerate(['person_clothing_level', 'wrong_instance_spatial', 'category_mismatch', 'ambiguous_ref', 'replace_is_attribute', 'ill_posed_edit', 'attribute_value', 'mask_quality', 'independence_violation', 'add_anchor', 'translation', 'grammar_style', 'ref_noref_mismatch'], 1):
    l = ex_by.get(cat, [])
    P(f'### 3.{ci} {CATZH[cat]}（`{cat}`，{len(l)} 条）')
    P('')
    P(CATDESC[cat])
    P('')
    picked = []; seen = set()
    for o in l:
        if o['case_id'] in seen: continue
        if o.get('current_instruction_ref') is None: continue
        picked.append(o); seen.add(o['case_id'])
        if len(picked) == 2: break
    for o in picked:
        ev = o.get('evidence_zh') or o['evidence']
        sf = o.get('suggested_fix') or {}
        fix = sf.get('instruction_ref') if isinstance(sf, dict) else None
        oth = (o.get('other_zh') or (sf.get('other') if isinstance(sf, dict) else None))
        P(f'- `{o["case_id"]}` {o["unit_id"]}（{SEVZH[o["severity"]]}）：当前 “{esc(o["current_instruction_ref"])}”。问题：{esc(ev)}' + (f' 建议：“{esc(fix)}”' if fix else '') + (f'；{esc(oth)}' if oth else ''))
    P('')
# ---------------- full list
P('## 4. 完整问题清单')
P('')
P('说明：按 case 分组；先列含阻断问题的 case，再列最严重为“严重”的 case，最后列仅含轻微问题的 case；组内按 manifest 顺序。“输入”为该单元正式评测输入形式（ref/noref + 定位）。“核验”列：**目视**=已在审图上核实；**文本**=仅自动文本规则发现。证据为中文译述（保留原英文指令、坐标）；建议中的英文为可直接替换的新指令。')
P('')
def fixtxt(o):
    sf = o.get('suggested_fix') or {}
    if not isinstance(sf, dict): return esc(sf)
    parts = []
    if sf.get('instruction_ref'): parts.append('Ref: ' + esc(sf['instruction_ref']))
    if sf.get('instruction_noref'): parts.append('No-ref: ' + esc(sf['instruction_noref']))
    oth = o.get('other_zh') or sf.get('other')
    if oth: parts.append(esc(oth))
    return '<br>'.join(parts)

def case_block(cid):
    c = byid[cid]
    l = sorted(bycase.get(cid, []), key=lambda o: (o.get('unit_id') or 'U0', SEV[o['severity']]))
    tl = sorted(txt_case.get(cid, []), key=lambda o: o.get('unit_id') or '')
    P(f'#### `{cid}`（#{order[cid]}，{RNGZH[rng(cid)].split("（")[0]}，最严重：{SEVZH[["blocking","major","minor"][worst(l)]] if l else "轻微"}）')
    P('')
    P('| U | 级别 | 类别 | 输入 | 当前指令 (Ref) | 问题 | 建议修改 | 核验 |')
    P('|---|---|---|---|---|---|---|---|')
    for o in l:
        P(f'| {o.get("unit_id") or "case"} | {SEVZH[o["severity"]]} | {CATZH.get(o["category"], o["category"])} | {o.get("formal_input") or ""} | {esc(o.get("current_instruction_ref"))} | {esc(o.get("evidence_zh") or o["evidence"])} | {fixtxt(o)} | 目视 |')
    for o in tl:
        sf = o['suggested_fix']
        fx = ('Ref: ' + esc(sf['instruction_ref']) + ('<br>No-ref: ' + esc(sf['instruction_noref']) if sf.get('instruction_noref') else '')) if sf.get('instruction_ref') else esc(sf.get('other'))
        P(f'| {o["unit_id"]} | 轻微 | {CATZH["grammar_style"]} | {o.get("formal_input") or ""} | {esc(o.get("current_instruction_ref"))} | {"add 指令含悬空 its/their（协议要求 payload 不含悬空 its）" if o["source"].endswith("its") else "add 物品过于笼统，未说明颜色/图案/文字"} | {fx} | 文本 |')
    P('')

P(f'### 4.1 含阻断问题的 case（{len(cases_bl)} 个）')
P('')
for cid in cases_bl: case_block(cid)
P(f'### 4.2 最严重为“严重”的 case（{len(cases_mj)} 个）')
P('')
for cid in cases_mj: case_block(cid)
P(f'### 4.3 仅含轻微问题的 case（{len(cases_mn)} 个，目视确认）')
P('')
for cid in cases_mn: case_block(cid)
P(f'### 4.4 仅有自动文本规则发现的轻微问题的 case（{len(txt_only_cases)} 个）')
P('')
P('以下 case 目视复核未记录问题，只有 add 指令悬空 its 或笼统 payload 的文本问题（未单独目视判定，但属于协议明确禁止的写法）。')
P('')
P('| case | U | 当前指令 (Ref) | 问题 | 建议 |')
P('|---|---|---|---|---|')
for cid in txt_only_cases:
    for o in sorted(txt_case[cid], key=lambda o: o['unit_id']):
        sf = o['suggested_fix']
        fx = ('Ref: ' + esc(sf['instruction_ref']) + ('<br>No-ref: ' + esc(sf['instruction_noref']) if sf.get('instruction_noref') else '')) if sf.get('instruction_ref') else esc(sf.get('other'))
        P(f'| `{cid}` | {o["unit_id"]} | {esc(o.get("current_instruction_ref"))} | {"悬空 its/their" if o["source"].endswith("its") else "笼统 add payload"} | {fx} |')
P('')
# ---------------- recommendations
P('## 5. 系统性改进建议')
P('')
P('### 5.1 应在构建管线中新增的校验器')
P('')
recs = [
 '**方位/序数校验**：解析 ref 中目标头名词自身的方位词（排除 “left of X” 等关系短语），与 box 中心比较；更关键的是利用 dense annotation 中同类别其他实例，验证 “leftmost/second from left/nearest/upper” 在同类候选中成立；不成立直接拒绝。本次 115 条自动命中中 78 条被确认。',
 '**人物层级校验**：scope/category ∈ 人物词时禁止 attribute/replace（除非 target_part 指明服装）；replace payload 为服装而 target 为人时拒绝；add 锚点为整个人时必须给出服装/身体部位并改用对应 mask。同时校验 `category=person` 的 mask 是否真的是整人（用 dense 标注类别或人体/服装分割模型），本批多例 “person” 实为衣服。',
 '**replace 类别变化校验**：payload 头名词与原 scope 同义/同类且修饰词仅为颜色/材质/图案/文字时，强制转为 attribute 或要求换成不同品类/结构；payload 无名词（“with blue”）直接拒绝。',
 '**无变化（no-op）校验**：在 mask 内测量主色（Lab 均值/主导色），与 attribute 目标色或 replace payload 颜色比较，ΔE 过小即拒绝（本次发现白车改白、黑灯改黑、红敞篷换红敞篷、已有头盔再加头盔等）。',
 '**ref 名词—mask 一致性校验**：用 VLM/开放词汇检测在 mask 裁剪上验证 ref 头名词与颜色词（“officer”→衬衫、“bottle”→水母、“sign”→灯笼等均可被拦截）；与 dense 标注的 source_category 交叉检查。',
 '**歧义校验**：统计 dense 标注中与目标同类别、且满足 ref 修饰语的实例数；>1 时要求加区分信息，尤其对 `ref+none`（纯文本定位）单元强制要求唯一性复核。',
 '**独立性校验**：利用 associations_json 及 mask 空间关系（服装/配件 mask 是否落在某人物 mask 或其外扩范围内）判断两个单元是否属于同一人/同一车；同一人身上的衬衫+袖子、帽子+包都应拒绝；检查单元间编辑依赖（删除的人手持另一单元目标）。',
 '**不可执行编辑规则**：禁止 remove 穿着中的上衣/外套/裙子（除非人台）、整栋建筑/桥/屋顶等大结构、载人的婴儿车/轮椅；add payload 必须是实物，禁止 glow/light effect；add 到已占用座椅、已有同类物（已有坐垫/头盔/花盆）时拒绝。',
 '**模板检测**：对 “the <noun> at/near the <方位>” 型 ref、generic payload（a small logo/badge/sign）、generic evidence（“是四个不同对象”）设阈值报警；一个 case 内多数单元为模板时整 case 退回人工撰写。',
 '**文本规范**：add 渲染器把 site 写成 “<relation> the <site> of <anchor>”，禁止悬空 its；中文由同一 spec 渲染并做颜色/方位/数量/操作一致性检查。',
]
for i, r in enumerate(recs, 1): P(f'{i}. {r}')
P('')
P('### 5.2 流程建议')
P('')
P('- 审核记录要与实际一致：尾段 2.5.0-draft 记录的 evidence/protection 为泛化模板，却与其他 case 同样标为 `ai_direct_visual` 并计入“全部经视觉审核”。建议区分“模板草稿”与“已逐图复核”，未复核者不得进入正式集合。')
P('- 每次修订后重新生成审图（原图 + 各 U 轮廓 + 局部放大）并逐 U 复核“ref 是否只指向该 mask”；对纯 ref 单元要求复核者在不看 mask 的情况下先按 ref 圈出目标，再与 mask 比对（盲测一致性）。')
P('- 引入独立人工抽检（至少每 20 case 抽 1 个，尾段全检），并在 `known_issues.json` 中登记本报告的阻断项。')
P('- replace 与 attribute 的边界、颜色词标准、方位词（图像坐标 vs 身体左右）写入撰写检查表。')
P('')
P('### 5.3 正式评测前建议排除/返工的 case')
P('')
tail = [c['id'] for c in cases if rng(c['id']) in 'CD']
excl = sorted(set(cases_bl) | set(c['id'] for c in cases if rng(c['id']) == 'D'), key=lambda c: order[c])
P(f'- **必须排除（直至修复并复核）**：所有含阻断问题的 case（{len(cases_bl)} 个，见 4.1 节）。')
P(f'- **建议整体退回重写**：尾段 #945–#1083 全部 139 个 case（模板化、{sum(1 for c in bycase if rng(c)=="D" and worst(bycase[c])<=1)}/139 有严重及以上问题）；#869–#944 的 76 个 case 建议逐条复核重写（{sum(1 for c in bycase if rng(c)=="C" and worst(bycase[c])<=1)}/76 有严重及以上问题）。')
P(f'- 两者并集共 **{len(excl)}** 个 case 建议暂不进入正式评测；在此之外，含“严重”问题的 case 应在修订后再评测，或在报告中单独标注。')
P(f'- 若需立即评测，可用的“相对干净”子集为：无任何阻断/严重问题且不在尾段的 case，共 {sum(1 for c in cases if worst(bycase.get(c["id"],[]))>=2 and rng(c["id"]) in "AB")} 个（仍可能含轻微措辞问题）。')
P('')
P(f'含阻断问题的 case（{len(cases_bl)} 个）：')
P('')
P(', '.join(f'`{c}`' for c in cases_bl))
P('')
P('known_issues.json 仅登记了 `v2-sa_9357354` 的 U1/U2；本次确认其 U1 的 “at the left” 实为画面右侧舞者（box x=1460–1907 / 2250），并新增大量同类问题（如 `v2-sa_9345888` U1/U2 的 “officer” 实为平民白衬衫、U3 “hat at the left” 实在右侧）。建议将本报告阻断项全部登记到 known_issues。')
P('')
P('建议排除 case 列表（阻断 ∪ 尾段 #945–#1083）：')
P('')
P(', '.join(f'`{c}`' for c in excl))
P('')
P('## 6. 产物与可复现性')
P('')
P('| 文件 | 内容 |')
P('|---|---|')
P('| `/tmp/samtok_audit/phaseA.py` / `auto_checks.json` | 阶段 A 规则脚本与全部命中、每单元 mask 统计 |')
P('| `/tmp/samtok_audit/render.py` / `views/` | 审图渲染脚本与 1,084 张合成审图 |')
P('| `/tmp/samtok_audit/batches/` / `agent_prompt.md` | 28 个目视审查批次的输入与审查规程 |')
P('| `/tmp/samtok_audit/agent_out/` | 每批目视结果（findings / reviewed，含被否定的自动 flag 及理由） |')
P('| `/tmp/samtok_audit/findings.jsonl` | 合并后的全部问题（每行一条：case_id、unit_id、severity、category、evidence、suggested_fix、verified_visually 等） |')
P('| `/tmp/samtok_audit/reviewed.txt` / `reviewed_meta.json` | 已目视的 case 列表（1,084）及每 case 审查摘要 |')
P('| `/tmp/samtok_audit/lead_spotcheck.jsonl` | 主审抽查记录 |')
P('')
open(OUT, 'w').write('\n'.join(L) + '\n')
print('written', OUT, len('\n'.join(L)))
print('missing translations', sum(1 for o in vis if not o.get('evidence_zh')))
print('excl', len(excl))
with open(A + '/findings.jsonl', 'w') as fo:
    for o in F:
        o2 = {k: v for k, v in o.items() if k != '_i'}
        fo.write(json.dumps(o2, ensure_ascii=False) + '\n')
print('findings rewritten with zh', len(F))
