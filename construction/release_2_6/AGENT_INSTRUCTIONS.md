# Release 2.6.0 repair instructions (for repair agents)

Repair-stage rules are retained for provenance. All 804 repair cases are complete; publishing and restore instructions are in `docs/RELEASE_2_6_0_ZH.md`.

You repair SAMTok benchmark cases for release 2.6.0. Two goals per case:

1. **Protocol 2.0 (blind no-ref)**. Spec: `docs/07_SAMTokEdit_Qwen21_指令协议2.0_noref改为盲指代.md`, sections 1–5, 7, 8. Read it first.
2. **Fix every audit problem** (`construction/release_2_6/audit/findings.jsonl`, report `docs/BENCHMARK_AUDIT_20261015_ZH.md`), and any further problem you find yourself while looking at the case.

Repo: `/opt/tiger/tanyue/samtok_edit_benchmark` (branch v2branch). Python: `/opt/tiger/envs/gen/bin/python`.
Base release (read only): `data/v2_1084/cases.jsonl`. Data root (read only except the work dir):
`/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2`. Work dir for masks:
`<root>/release_2_6_work/<case_id>/`.

**Never modify** `data/v2_1084/*`, files under `<root>/assets/`, other agents' revision files, or code. Only write
your own `construction/release_2_6/revisions/<case_id>.json`, files in `<root>/release_2_6_work/<your cases>/`, and
your log file. Use only your assigned GPU (`export CUDA_VISIBLE_DEVICES=<gpu>`). Do not run full builds.

---

## A. What protocol 2.0 changes

- **No-ref is rendered automatically** by `render(spec, False)` and is always blind: `Change the color of the
  selected region to navy blue.`, `Replace the selected region with <payload>.`, `Remove the selected region.`,
  `Add <payload> <relation> the selected region.` You never write the English no-ref yourself.
- Therefore **the "what" must be self-contained**: payload, attribute value, relation and result phrase may not
  depend on the "where". No dangling `its/it/the same/a matching one` in payloads ("a small emblem at its right end"
  → put "right end" in `placement.site` and make the mask that end; payload "a small emblem").
- **Source mask = the region actually edited (T)**. ref and no-ref share it; box/point are derived from it.
  - edit a whole object/part: that object/part (usually unchanged);
  - attribute/replace with `target_part`, remove `part`: the part itself;
  - remove `lowerlegs`/`hem`: only the cut-off lower segment; remove `contents`: container ∪ contents;
    `contents_only`: the contents;
  - **add**: the attachment site of the new item, i.e. the existing support region (not the new item's outline).
    Without `placement.site` the site is the selected anchor object (unchanged). With a site (e.g. "the handle of
    the suitcase", "the upper back of the jacket") the mask becomes that site only.
- Every unit whose 2.5.0 spec has `target_part`, a non-`whole` `remove_mode`, or an add `placement.site` **must get
  a reviewed `<unit>_v2.png`** (299 units overall). If segmentation is truly impossible, add
  `"mask_exemption": "<reason>"` to that unit's revision (rare; it becomes a known issue).
- `instruction_ref` must stay byte-identical for units you do not revise.
- Chinese no-ref (`instruction_noref_zh`) always uses **选中区域**, e.g. `将选中区域的颜色改为海军蓝。`, `将选中区域替换为喇叭袖。`,
  `移除选中区域。`, `给选中区域加上一枚小圆形珐琅徽章。`. The builder derives it from the Chinese ref when the pattern is
  standard; provide it explicitly when you revise unusual sentences.

## B. Benchmark authoring rules (README §3–5 + style)

- 2–5 units per case, each on a **different physical parent object** (not two parts of one person/object; a worn
  accessory such as a backpack may be separate from its wearer). Keep mask overlap between units ≤ 4%.
- Each ref is ONE concise noun phrase that identifies exactly one instance **verified in the image**: shortest
  modifier that excludes the nearest rival (owner, position, colour, ordinal with its counting group/direction).
  Use image-left/image-right when body sides are confusing. No "which is…", no exclusion lists, no "preserve…".
  Ref ≲ 26 words. Check colours on the clean source, not the overlay.
- Operation semantics:
  - **replace** = real category/structure change of the same object level ("sleeve → flared bell sleeve"); a colour
    or material change only is **attribute**. Per user decision: prefer rewriting the payload into a genuine,
    natural structural replacement (keeps the replace/attribute balance); convert to attribute only when no natural
    structural replacement exists. Never replace a person with clothing.
  - **attribute** names property + a value that differs visibly from the current state (no "white car → white",
    no vague "to dark"). Never recolour a whole person: name the garment, and the mask must be that garment.
  - **remove** names the extent; no removing a garment someone wears, or a whole building/bridge, or anything
    whose removal is physically absurd.
  - **add** = a natural item directly on/attached to the selected support, with count; no adding what already
    exists (helmet on a helmeted person).
- Edits must be natural and feasible; two units must not conflict (e.g. one recolours what another removes).
- Chinese fields (`ref_zh`, `instruction_ref_zh`, `scope_zh`, `physical_parent_zh`) must match the English.

## C. Allowed repair actions (user decisions, 2026-10-15)

In this order of preference, per unit:
1. **Rewrite** the instruction (ref / scope / payload / operation / attributes / placement), keeping the mask if it
   is the correct edited region.
2. **Fix the mask** (SAM3-assisted, visually verified) when the instruction is right but the mask is wrong or too
   coarse (e.g. "shirt" but mask is the whole person → segment the shirt).
3. **Retarget**: choose another clearly visible, independent object in the same image, segment it with SAM3, verify
   it visually, and write a new unit on it (keep the unit id and its interaction form; keep the case's operation
   mix balanced: prefer the same operation).
4. **Drop the unit** only if 1–3 fail; the case must keep ≥2 units and ≥2 distinct interaction forms.
5. **Drop the case** (`"action": "drop_case"`) only if the image cannot support 2 valid units. Very rare.

Tail cases **#945–#1083** (index in `data/v2_1084/cases.jsonl`, 0-based) are template-written: **re-examine and
rewrite every unit** (precise refs, correct masks, natural edits), not only listed findings.
For other cases: fix all listed findings (blocking, major and minor) and anything else wrong you notice. If you judge
a finding to be a false positive, say so with evidence in your log; do not silently skip it.

## D. Tools

```bash
cd /opt/tiger/tanyue/samtok_edit_benchmark
S="/opt/tiger/envs/gen/bin/python construction/release_2_6/segment.py"
$S show --case C               # case sheet: all unit masks (v2 if committed) -> <work>/C/case_sheet.jpg
$S show --case C --unit U2     # + zoom with a grid in ORIGINAL source pixels (read boxes/points from it)
$S text --case C --unit U2 --text "handle"                 # SAM3 concept segmentation inside the unit's 2.5.0 mask
$S text --case C --unit U2 --text "jacket" --within none --box x1 y1 x2 y2   # outside the host (retarget/fix)
$S prompt --case C --unit U2 --box x1 y1 x2 y2 [--pos x,y ...] [--neg x,y ...]  # SAM3 tracker (one object)
$S compose --case C --unit U2 --expr "t1_2|t1_3" [--and-host] [--and-box x1 y1 x2 y2] [--minus-box ...] [--minus-unit U1]
$S compose --case C --unit U2 --and-box x1 y1 x2 y2        # no --expr: host ∩ box (region-type add sites, lower legs, hem)
$S commit --case C --unit U2   # writes <work>/C/U2_v2.png from the last compose (only after viewing final.jpg)
/opt/tiger/envs/gen/bin/python construction/release_2_6/build.py --check-only --cases C [C2 ...]
```

- Candidate sheets (`<tag>.jpg`) number each candidate; the gray outline is the unit's 2.5.0 mask (host).
- **Always Read the sheet images** (case_sheet, candidate sheet and final.jpg) and check the mask covers exactly the
  edited region, with occluders and holes excluded and no neighbour included. Masks are proposals until you
  have looked. Region-type sites ("upper back", "lower portion") are host ∩ a box you choose on the grid.
- Retarget/whole-object fixes: `text --within none --box ...` or `prompt --box ... --pos ...`; then `compose
  --expr <cand>` (+ `--minus-unit` to avoid overlaps) and `commit`.

## E. Revision record: `construction/release_2_6/revisions/<case_id>.json`

```json
{
  "case_id": "v2-sa_…",
  "reviewer": "<your agent name>",
  "notes": "short case-level note",
  "reviewed_views": ["release_2_6_work/<case>/case_sheet.jpg", "…/U2/final.jpg"],
  "difficulty": {… optional full replacement of the case 'difficulty' object if its evidence text is now wrong …},
  "action": "drop_case",            // only for case removal; then add "reason"
  "units": [
    {"id": "U1", "action": "keep"},                                   // unchanged instruction (mask may be v2)
    {"id": "U2", "action": "revise",
     "spec": {"ref": "…", "scope": "…", "payload": "…", "operation": "…", "attributes": [{"property": "color", "value": "…"}],
              "target_part": "", "remove_mode": "whole", "placement": {"relation": "on", "site": "…"}, "qualifier": ""},
     "ref_zh": "…", "scope_zh": "…", "physical_parent_zh": "…", "parent_instance_id": "sa_<id>:<中文父对象名>",
     "instruction_ref_zh": "…", "instruction_noref_zh": "… (optional; must use 选中区域)",
     "preserve": ["… optional updated protection list …"],
     "findings_addressed": ["wrong_instance_spatial", "…"], "reason": "…"},
    {"id": "U3", "action": "drop", "reason": "…"}
  ]
}
```

- `spec` contains only the fields you change (others are kept from 2.5.0). Spec rules: `remove` has empty payload;
  `remove_mode=part` needs `target_part`; add needs `placement` with a relation from the protocol list (`to, on, in,
  inside, around, across, along, over, attached to, clipped to, hanging from, resting on, mounted on, sewn onto,
  tied around, pinned to, hooked over, strapped over`); a site needs a relation other than `to`; attribute needs
  `attributes` (property ∈ color, material, finish, pattern, texture, text, tint, opacity) and empty `target_part`
  unless editing a part (then the mask is that part).
- Units listed as `keep` or omitted keep 2.5.0 text. A committed `<unit>_v2.png` is used automatically.
- Retarget = `revise` + new spec/zh/parent fields + committed v2 mask. You may change `"interaction"` only when a
  drop forces it (keep ≥2 forms).
- Worked example (already done): `construction/release_2_6/revisions/v2-sa_9345888.json`; protocol-only mask
  example: case `v2-sa_2566092` (U1 = chest emblem by `text "white emblem"`, U3 = shoulder site by host ∩ box).

## F. Per-case procedure

1. Read the case record and its findings (`grep '"case_id": "<C>"' construction/release_2_6/audit/findings.jsonl`).
2. `show --case C` and Read the sheet; zoom on each unit you touch (`show --unit`). Look at the clean image
   regions, not only the overlay.
3. Decide each unit (keep / revise / fix mask / retarget / drop). Produce required v2 masks and look at each
   `final.jpg` before `commit`.
4. Write the revision JSON (skip the file only if the case needs nothing: no findings, no S≠T unit, not tail).
5. `build.py --check-only --cases C` until it prints `ok_check_only`; fix every problem it lists.
6. Append one JSON line to your log `construction/release_2_6/logs/<agent>.jsonl`:
   `{"case_id","units":{"U1":"keep|revise|mask_v2|retarget|drop", …},"findings_fixed":[…],
   "findings_rejected":[{"unit","category","why"}],"new_problems_found":[…]}`.

Work through your whole assignment. Keep going until every assigned case passes `--check-only`. At the end, report
counts (cases touched, units revised/retargeted/dropped, v2 masks, cases dropped, findings rejected with reasons)
and any case you could not resolve.
