# Release 2.6.0 剩余待修复 case 清单（自动生成）

> 由 `construction/release_2_6/status.py` 于 2026-10-16T07:47:31+00:00 生成，只读取修订文件、日志、work 目录 mask 和 2026-10-15 审查结果（`construction/release_2_6/audit/findings.jsonl`），没有重新看图。修复后重新运行即可刷新。
>
> 审查给出的“建议修改”中的 no-ref 写法已过时：协议 2.0 的 no-ref 由 `render(spec, False)` 自动生成为 `the selected region`，只需改 spec、ref、中文和 mask。replace 实为换色的问题按用户决定优先改成真实结构替换。

## 汇总

| 状态 | case 数 |
|---|---:|
| 已完成（修订 + 日志 + 检查通过） | 804 |
| 已写修订且检查通过，但缺日志 | 0 |
| 已写修订但检查未通过 | 0 |
| 进行中：已有 v2 mask，无修订文件 | 0 |
| 未开始 | 0 |
| 无需处理 | 280 |

未完成 case（缺日志、检查未通过、进行中、未开始）共 0 个，其中的审查问题：阻断 0、严重 0、轻微 0 条；协议 2.0 仍需换部件/附着部位 mask 的单元 0 个（全库共 299 个）。

| 类别 | 未完成 case 中的条数 |
|---|---:|

## 1. 已写修订但检查未通过（0 个）


## 2. 进行中：已有 v2 mask，但没有修订文件（0 个）


## 3. 未开始（0 个）


## 4. 已写修订且检查通过，但缺日志（0 个）

修复 agent 可能在写日志前中断。请确认修订是否完整，再补日志或重修。


## 5. 已完成 case 中被否定的审查问题（41 条，来自修复日志）

| case | 单元 | 类别 | 否定理由 | 日志 |
|---|---|---|---|---|
| `v2-sa_10119096` |  | independence_violation | U1 is the worn backpack, U2 the coat; AGENT_INSTRUCTIONS rule B explicitly allows a worn accessory such as a backpack as a separate physical parent from its wearer. Coat mask excludes the backpack (0 overlap), edits do not conflict, parent_instance_ids already distinct. | shard1 |
| `v2-sa_10367798` | U1 | ambiguous_ref (suggested fix only) | Suggested upper-left is wrong: the two small bulbs by the skylight are higher; U1 is the large foreground globe at the far left (x~0.07W), so ref uses far left instead. | shard1 |
| `v2-sa_1165283` | U2 | mask_quality | Enlarged clean source and original-mask contour show the turquoise bag and navy scarf excluded. The mask separates exposed red shirt regions above/below bag and at its side; no bag surface filled. | round2 |
| `v2-sa_1165283` | U2 | mask_quality | Enlarged clean source and original-mask contour show the turquoise bag and navy scarf excluded. The mask separates exposed red shirt regions above/below bag and at its side; no bag surface filled. | round2 |
| `v2-sa_168719` | U1 | mask_quality | Hand-inclusion claim is false: original source selector has an explicit hand-shaped notch. SAM3 fork proposal is also disjoint from accepted floral selection. Drape fragments/boundary were still cleaned using floral selection and curtain subtraction. | round2 |
| `v2-sa_190256` | U3 | independence_violation | AGENT_INSTRUCTIONS B expressly allows worn accessories separate from wearer. Bag is a discrete object; measured U2/U3 overlap 90 px, 0.28% of smaller mask, and shirt mask excludes strap. | round2 |
| `v2-sa_1923359` |  | independence_violation | Bag is discrete worn accessory, expressly permitted separate from wearer in AGENT_INSTRUCTIONS B. Skirt and bag masks do not overlap appreciably. | round2 |
| `v2-sa_2264516` | U2 | independence_violation | AGENT_INSTRUCTIONS explicitly allows a worn backpack as separate object. Source shows accessory backpack and jacket as distinct physical objects; masks overlap by 0 pixels despite overlapping boxes. | round2 |
| `v2-sa_2553111` | U3 | independence_violation | The pink package (box ~300-600 x 535-805 display) is a separate loose object clutched by the boy, not a part of him or his shorts (U1, y~920-1160); masks do not overlap; carried objects count as separate parents like a backpack. Audit itself marked it acceptable. | shard1b |
| `v2-sa_271071` | U3 | independence_violation | crossbody bag (box 1971-2169 x 674-881) is a separate worn accessory, allowed by rule B; U1/U3 mask overlap is 71 px (0.5% of U3), edits do not conflict | shard1b |
| `v2-sa_2734741` | U3 | category_mismatch | clean-source zoom of box 1573-1640 x 1091-1150 shows a clear plastic bottle on its side: radial pattern is the petaloid bottle base, cylindrical body and neck extend to the right; not a jellyfish | shard1b |
| `v2-sa_2858888` | U3 | independence_violation | U3 is the worn black backpack, a worn accessory which AGENT_INSTRUCTIONS B allows as a separate parent from its wearer's shirt (U2); masks overlap only 3 px (U2 28096 px, U3 111988 px), edits (shirt->hoodie, patch on backpack) do not conflict | shard1b |
| `v2-sa_2989808` | U4 | independence_violation | The raised trophy and medal are distinct detachable physical objects; common wearer/holder does not merge them. Their source masks have 0 overlapping pixels. Medal removal does not affect trophy recoloring. | round2 |
| `v2-sa_2989808` | U4 | independence_violation | U1 trophy (box 890-1116 x 28-577, held overhead) and U4 medal (box 903-1014 x 873-1319, on ribbon at chest) are distinct physical objects with distinct parent ids, zero mask overlap, and non-conflicting edits (recolour trophy vs remove medal); finding itself rates it weak coupling. Alternatives are worse: far-right medal is half occluded by the plush elephant ear, other medals belong to U2/U3 ath… | shard1b |
| `v2-sa_3171541` | U2 | mask_quality | Partially rejected: original zoom and mask pixels show bag body (1640,1300), (1650,1310) and hand (1570,1285), (1555,1290) already excluded. Strap inclusion was valid and fixed; 297 strap pixels belonged to original mask but none to new coat candidate. | round2 |
| `v2-sa_3460138` | U3 | independence_violation | White plastic bag is a detachable hand-held object distinct from the purple jacket; masks do not overlap. Jacket color change and bag removal do not affect each other, as the audit also acknowledges. | round2 |
| `v2-sa_3928896` | U2 | mask_quality | Original host already excludes dark diagonal strap and satchel, visible as uncolored notch in U2 sheet; claim that host includes bag/strap is false. Nevertheless new sleeve-only support mask and explicit image-left site resolve coarse site selection. | round2 |
| `v2-sa_4216048` | U2 | mask_quality | Clean source: the lowest wire is only visible from ~x2240,y325 (where it clears the tree line) to ~x2745,y275 (right tree); mask box 2242-2743 x 268-330 covers that whole visible span; further left it is invisible against foliage. | shard2 |
| `v2-sa_4477450` | U1 | replace_is_attribute (mask sub-claim: clips red bag) | SAM3 red bag box [1743,1225,1783,1303] has only 0.7% of its pixels inside the dress mask; the mask already excludes the bag | shard2 |
| `v2-sa_4550787` | U2 | mask_quality | High-res overlay (x600-1100,y850-1150) shows the clasped hands and black cuff are in neither U1 nor U2 mask; U2 is the maroon vest panels only. | shard2 |
| `v2-sa_4999349` | U1 | mask_quality | Strip at x~1395-1415,y~1420-1495 is the metal ring and black zipper-pull strap hanging from the backpack itself (visible on clean source), so it belongs to the removed object. | shard2 |
| `v2-sa_6014866` | U3 | mask_quality | partially false positive: the camera body (src ~400-500 x, 2030-2160 y) is outside the 2.5.0 mask, which already has a notch around it; only the thin Nikon strap was inside, and it is now subtracted | shard2b |
| `v2-sa_610993` | U1 | mask_quality | Viewed source and overlay: jacket mask follows sleeves/lapels and open side panels; central black crop top and necklace are excluded, contrary to audit claim. | round2 |
| `v2-sa_6400522` |  | independence_violation | Cameo portrait brooch is a separately pinned physical accessory (own sa_6400522:portrait_brooch parent), not fabric. Rule B permits worn accessories separate from wearer. Brooch on chest and sleeve at image-left have disjoint masks; edits do not conflict. | round2 |
| `v2-sa_654776` |  | independence_violation | U2 is a removable baseball cap; U3 is a separately worn backpack with gold carabiner. Rule B permits worn accessories as separate physical parents. The two masks are spatially disjoint (cap y1007-1145, bag y1192-1500), and removing backpack does not conflict with cap recolor. | round2 |
| `v2-sa_6561145` | U1 | mask_quality | Audit factual claim that original host includes driver upper body is false: original U1 sheet has an explicit notch excluding head/torso, and SAM3 person proposal lies 92.6% outside host. Nevertheless removal changed to contents mode and driver mask union to avoid an unsupported floating person. | round2 |
| `v2-sa_6791309` | U3 | mask_quality | Clean enlarged hanging_detail.jpg shows burgundy sleeves continuing into matching gray ribbed cuffs, both part of one top. The separate long black garment at image-left lies outside U3 mask; the alleged separate dark sleeve is a cuff. | round2 |
| `v2-sa_6992576` | U2 | category_mismatch | Partly false: the glass base is detached and stands alone on the bench with an open neck; the brass stem belongs to a separate hookah and the pink/blue hose only passes in front, so replacing it would not leave a floating stem. Ref/payload were still rewritten (not beside the baskets; vase payload too close to material change). | shard3 |
| `v2-sa_7052077` | U2 | ambiguous_ref (mask part) | Zoom shows the U2 mask boundary notches around the pink bicycle crate (x~690-725, y~1205-1250); the crate is excluded, so no mask trim needed. | shard3 |
| `v2-sa_7362739` | U4 | mask_quality | The orange life ring is already a hole in the railing mask: SAM3 life-ring mask (x307-408,y649-744) has frac_in_host 0.0; the case sheet shows the ring outlined as excluded. | shard3 |
| `v2-sa_7381987` | U4 | ambiguous_ref (mask part: tighten bottom to exclude vats) | Zoomed overlay: the mask lower edge follows the diagonal boundary of the building lower wall (x 230-560, y 700-850) and stops where the vat platforms begin; no vat is included. | shard3 |
| `v2-sa_7810159` | U4 | mask_quality | Not two megaphones: one megaphone carried under the forearm (cream bell + blue body/handle + coiled cord); the forearm occlusion splits the mask into pieces. Mask kept; vague noun/payload fixed. | shard4 |
| `v2-sa_8188123` | U3 | category_mismatch (mask part) | claim that the mask includes the sunbathing woman head is false: at 4x zoom the mask boundary notches around her head; mask kept | shard4 |
| `v2-sa_8336561` | U1/U3 | independence_violation | 2.5.0 U1 mask already had a hole at the U3 card: pixel overlap U1&U3 = 0 (checked numerically); new felt-only U1 v2 mask (rail, cards, chips excluded) also has zero overlap | shard4 |
| `v2-sa_838336` | U2 | person_clothing_level | accepted, but the suggested fix (attribute->blue) was not used; kept replace op with a garment-level structural replacement (red puffer jacket -> denim jacket) per the replace-balance rule | shard5 |
| `v2-sa_8405850` | U2 | replace_is_attribute | accepted; suggested fix (convert to attribute material) not used; kept replace with a genuine building-level replacement per replace-balance rule | shard5 |
| `v2-sa_8429220` | U2 | replace_is_attribute | accepted problem but fixed by structural replace (shirt -> grey hooded sweatshirt) instead of suggested attribute conversion, per replace-balance rule | shard5 |
| `v2-sa_8430740` | U3 | mask_quality | mask itself is correct (printed sandwich graphic); fixed by rewriting the ref to say printed sandwich on the banner | shard5 |
| `v2-sa_8962292` | U4 | independence_violation | minor; finding itself says acceptable: the plastic bag is a separate object hanging from the handlebar, hat is worn accessory, bicycle separate; edits (recolour bike, sticker on bag, remove hat) do not conflict and masks do not overlap | shard6 |
| `v2-sa_9111693` | U4 | ambiguous_ref (mask holes part) | the internal hole is the womans black handbag occluding the coat; excluding it is correct, mask kept | shard6 |
| `v2-sa_9161358` | U4 | mask_quality | the second mask component (x~880-944, y~700-760) is the right end of the same sign (letters AK) visible through the bougainvillea, verified on a clean crop; not a stray blob | shard7 |

## 6. 修复时在审查清单之外额外发现的问题（745 条，来自修复日志）

这些是修复 agent 自己发现的问题，按要求通常已在同一份修订中处理，列出仅供追溯；不是剩余工作。

- `v2-sa_10006079`（shard1）：U1 tank top is yellow with small print; ref now names colour
- `v2-sa_10109700`（shard1）：U4 add site neck: v2 mask committed (bottle neck)
- `v2-sa_10146830`（shard0）：U3 Chinese ref/noref carried the site (后背上部) and extra occlusion wording; cleaned zh fields
- `v2-sa_10175525`（shard0b）：U4 site outer thigh did not say which leg; set to image-right outer thigh to match v2 mask
- `v2-sa_1018156`（shard0）：U3 derived zh no-ref kept site word; explicit blind zh given
- `v2-sa_10198632`（shard0b）：U4 site did not say which sleeve; now upper image-left sleeve
- `v2-sa_10207017`（shard0b）：U4 middle front-row drummer ambiguous among 6 front-row drummers; now third from the right
- `v2-sa_10232066`（shard0）：U3 image-left lapel already has a blue pin; site moved to image-right lapel, payload made distinct
- `v2-sa_10232066`（shard0）：U3 zh no-ref carried site
- `v2-sa_10232066`（shard0）：U1/U4 zh ref mismatches
- `v2-sa_10308802`（shard1）：U1 silver hubcap nearly invisible on existing silver alloy rim; payload -> bright red hubcap
- `v2-sa_10342974`（shard1）：U2 the oven ambiguous (second compact oven in right tall cabinet); ref now the built-in oven under the countertop
- `v2-sa_10342974`（shard1）：U2 add site handle: v2 mask committed (door handle bar)
- `v2-sa_10342974`（shard1）：U1 ref middle pendant shade ambiguous; changed to second of three from the left (lead spot-check)
- `v2-sa_10367798`（shard1）：U2 upper-right inaccurate -> far right
- `v2-sa_10367798`（shard1）：U2 globe already opal-like glass, add shade near no-op -> red silk tassel hanging from it
- `v2-sa_10444816`（shard1）：U1 wearer called a boy but is a young man; ref made precise with NEW YORK print
- `v2-sa_10466790`（shard0b）：U3 auto Chinese no-ref kept site 手背; explicit blind zh given
- `v2-sa_1054426`（shard0）：U3 ref ambiguous vs second bicycle at right end of bar
- `v2-sa_1054426`（shard0）：U3 ref_zh mentioned handlebar not in EN ref
- `v2-sa_10688179`（shard1）：U2 pole top already holds a green mug; site changed from top to upper end (attached to), mask_v2 = upper pole segment
- `v2-sa_10706214`（shard1）：U3/U4 central hiker ambiguous (bib-480 hiker nearer center); refs now name hiker in purple T-shirt
- `v2-sa_10716780`（shard1）：U1 ref called the white-framed, orange-towelled lounger orange; simplified to the nearest lounger
- `v2-sa_10733610`（shard1）：U3 instruction_ref_zh missing 里 (fixed)
- `v2-sa_10781767`（shard0）：U2 added a reflective border that already exists (yellow backplate border); site housing = whole light
- `v2-sa_10781767`（shard0）：U1 middle traffic light ambiguous with 4th light on far-left pole
- `v2-sa_10790861`（shard1）：U3 handlebar site occluded by hand/bag/existing cup; site moved to padded crossbar
- `v2-sa_10803169`（shard1）：U1 payload duplicated existing number 11 (now checkered-flag decal)
- `v2-sa_10803169`（shard1）：U3 zh text value unquoted
- `v2-sa_10803560`（shard1）：U1 neck site is a region (host∩box), SAM3 had no neck candidate
- `v2-sa_10813555`（shard1）：U3 cab-roof v2 mask is small (438 px) because the mixer is distant
- `v2-sa_10831959`（shard0）：U3 ref behind on the right inaccurate (woman level at right of group)
- `v2-sa_10831959`（shard0）：U3 zh no-ref carried site
- `v2-sa_10831959`（shard0）：U4 zh ref mismatch (蓝绿色/missing 左) and missing 的颜色
- `v2-sa_10876982`（shard0）：U3 ref lacked center though front-left runner also has a waist pack; ZH had 中间
- `v2-sa_10876982`（shard0）：U1/U5 v2 masks committed (sleeves / image-left sleeve)
- `v2-sa_10883561`（shard0b）：U3 2.5.0 mask had a stray fragment on another chair; cleaned
- `v2-sa_10883561`（shard0b）：U5 auto Chinese no-ref named the site; explicit blind zh
- `v2-sa_1093348`（shard1）：finding evidence partly wrong: object at x760-800,y900-960 is mostly the same dish feed arm/LNB; ref strengthened anyway
- `v2-sa_10965932`（shard1）：U4 site mask is a thin ~480px strip (sign is tiny)
- `v2-sa_11030473`（shard0b）：U1 removed a worn sock (no-removing-worn-garment rule); retargeted to the carried axe
- `v2-sa_11030473`（shard0b）：U4 auto Chinese no-ref named the site; explicit blind zh
- `v2-sa_11071167`（shard0b）：U2 auto Chinese no-ref named the site; explicit blind zh
- `v2-sa_11072880`（shard1）：U1 2.5.0 mask had a 7px stray component on the neighbouring jacket (removed in U1_v2)
- `v2-sa_1110518`（shard1）：U3 ref "the woman’s black blazer on the right" could match another woman in black up-right; tightened to the pink-shirted woman
- `v2-sa_11136335`（shard1）：U4 lamp has five lanterns, not three (ref fixed)
- `v2-sa_11170556`（shard1）：U4 lantern already has a red bead hanging below; red tassel payload replaced by a small brass bell
- `v2-sa_11170556`（shard1）：U1 kimono mask has a tiny stray fragment near the hem (left as is, negligible)
- `v2-sa_1141051`（shard0b）：U2 mask included a stray blob on the vest (radio clip); removed
- `v2-sa_1165283`（round2）：U4 shoulder site clarified as image-left.
- `v2-sa_1165283`（round2）：U4 shoulder site clarified as image-left.
- `v2-sa_1165283`（round2）：Parent spot check: U3 original white-shirt mask included 231 px of brown bag strap. Subtracted reviewed SAM3 strap mask; v2 final reviewed then committed.
- `v2-sa_1199651`（shard1）：U3 site chest pocket ambiguous (two pockets) -> image-right chest pocket
- `v2-sa_1199651`（shard1）：U1 middle men counting group made explicit
- `v2-sa_1201946`（round2）：U3原mask有405/30/1像素非上衣组件，已删除并提交v2。
- `v2-sa_1204710`（shard1）：U2 replace payload was colour-only (skirt already ruffled flamenco) -> plain red knee-length A-line skirt
- `v2-sa_1212104`（shard1）：U4 car is a BMW X6 coupe-SUV, not sedan -> black car
- `v2-sa_1247398`（shard1）：U2 ref on the right not unique (another green trampoline behind at right) -> at the lower-right corner
- `v2-sa_1254142`（round2）：U4 blue-shirt replacement mask included diagonal shoulder-bag strap; SAM3 strap subtracted.
- `v2-sa_1254142`（round2）：U4 blue-shirt replacement mask included diagonal shoulder-bag strap; SAM3 strap subtracted.
- `v2-sa_1254142`（round2）：U4 replacement explicitly changed to long-sleeved turtleneck for clear structural change.
- `v2-sa_1301427`（shard1）：U3 ref central rider imprecise (man at 0.4W straddling parked black motorcycle) -> rewritten
- `v2-sa_1318943`（shard1）：U1 car is silver not white and a silver sedan sits further left behind the boat -> ref rewritten
- `v2-sa_1408122`（shard1）：U1 wearer gender unclear (long hair) -> ref by visible traits
- `v2-sa_1408122`（shard1）：U2 white shirt not directly beside puffer jacket -> ref rewritten
- `v2-sa_1411984`（shard0）：U4 zh ref mentioned a cap wearer not in English; zh no-ref carried shoulder site
- `v2-sa_1467894`（round2）：U1 old coat mask overlapped U3 handle >4%; retargeted U1 to separate wearer
- `v2-sa_1539716`（shard0b）：U5 ref ambiguous with a second white cap at x60-120,y727-755; site side->front since the cap faces the camera
- `v2-sa_1571336`（shard1）：U3 ref said just left of the post but cover straddles the post
- `v2-sa_1571336`（shard1）：U2 cabin roof is a canvas top
- `v2-sa_1572095`（shard1）：U1 navy on near-black blazer barely visible
- `v2-sa_1572095`（shard1）：U2 blazer->blazer replace was attribute-like
- `v2-sa_1572095`（shard1）：U3 clutch is cream not gold
- `v2-sa_1572241`（shard0b）：U4 site hip did not say which; set image-left hip to match v2 mask
- `v2-sa_157822`（shard1）：U3 payload identical to existing black globe lamp
- `v2-sa_157822`（shard1）：U1 lifebuoy already present on tug; site is upper deck railing
- `v2-sa_1580699`（shard0）：U2 ref said pale-green; clean source shows a clear package with dried squid at the far left edge
- `v2-sa_1580699`（shard0）：U3 zh no-ref carried site
- `v2-sa_161512`（shard1）：U1 mask had stray speck on hand (removed in v2)
- `v2-sa_161512`（shard1）：U2 shirt is pale gray, not white
- `v2-sa_1647901`（shard1）：U2 pale blue on pale bluish-white shirt barely visible
- `v2-sa_1659747`（shard1）：U1 replace hatchback->hatchback was recolor only; payload now a small silver pickup truck
- `v2-sa_1659747`（shard1）：U2 site lower corner ambiguous; now lower image-right corner
- `v2-sa_167171`（round2）：U1 existing slat bench to wooden slat bench was material-only; structural replacement supplied
- `v2-sa_167171`（round2）：U1 existing slat bench to wooden slat bench was material-only; structural replacement supplied
- `v2-sa_167171`（round2）：Parent spotcheck: disconnected U1 fragment on occupied bench removed; U1_v2 committed after final review.
- `v2-sa_168719`（round2）：U1 original replacement only changed rose colors/mix; rewritten as circular calla-lily wreath.
- `v2-sa_1691871`（shard0）：U1 Chinese no-ref would have leaked the site (横接前腿); zh fields rewritten
- `v2-sa_1752343`（round2）：Fine foreground fence rails cross the three car masks; SAM3 fence proposal was solid and not committed.
- `v2-sa_1752343`（round2）：Foreground fence rails crossed all three source masks; fixed by source-pixel geometric fine strip subtraction following failed solid SAM3 fence segmentation.
- `v2-sa_17741`（round2）：U3 original mask merged two sacks; SAM3 isolated left sack and ref now distinguishes it.
- `v2-sa_1785579`（shard0b）：U1 physical_parent_zh said 220 instead of 120
- `v2-sa_1785579`（shard0b）：U2 ref ambiguous with the 200 tray at the left; site made explicit as the two end walls
- `v2-sa_1799039`（round2）：U2 replace changed only color; replaced estate payload with compact panel van.
- `v2-sa_1799039`（round2）：U4 orange lifebuoys already exist at bow and cabin side; changed to blue anchor emblem on clear upper-left cabin panel.
- `v2-sa_1850053`（round2）：U2 rectangular sign to unspecified wooden sign only changed material/content; round hanging sign now changes structure.
- `v2-sa_1858329`（round2）：U2 replacement changed only color; rewrote as hooded poncho.
- `v2-sa_1863775`（round2）：U1 plastic spool replacement only changed material; rewrote with open spoked flanges; subtracted central aperture and two smaller holes.
- `v2-sa_1863775`（round2）：U2 white inventory labels already exist; replaced payload with orange triangular inspection sticker on clear wooden area.
- `v2-sa_1901719`（shard0b）：U1 outer thigh did not say which leg; set image-right
- `v2-sa_1901719`（shard0b）：U4 nearer ankle ambiguous; set image-right ankle
- `v2-sa_190256`（round2）：U2 replace only changed color/material; now collared short-sleeved shirt.
- `v2-sa_190256`（round2）：U3 beside ref inaccurate; now worn by specified man.
- `v2-sa_1904012`（round2）：U4 replace原仅颜色变化，已改结构替换。
- `v2-sa_1905152`（shard0）：U1 person at the left ambiguous with far-left foreground person; ref narrowed to back left
- `v2-sa_1923359`（round2）：U2 blue bag ref also fits adjacent light-blue bag; now dark-blue bag of brown-leather-jacket woman.
- `v2-sa_1939144`（round2）：U1原车后架被后袋遮挡，分割未成功，retarget独立长凳。
- `v2-sa_1939144`（round2）：U1原车后架被后袋遮挡，分割未成功，retarget独立长凳。
- `v2-sa_1957971`（shard0b）：U5 ref said just right of center but target is at ~0.74W; re-anchored on cream fur coat
- `v2-sa_200777`（round2）：U3 roof surface almost edge-on; SAM3 roof query no candidates. Rewrote add to small brass nameplate on visible upper front wall and committed exact attachment site.
- `v2-sa_200777`（round2）：U4 original boat mask included foreground leaf occluders. Subtracted reviewed SAM3 leaves/leafy-branch candidates.
- `v2-sa_2012261`（round2）：U4 lower corner unspecified; now image-left with matching site mask.
- `v2-sa_2052480`（round2）：U2 plastic bag to brown paper bag was only material/color; replaced payload with crushed cardboard box.
- `v2-sa_2053334`（shard0）：U2 zh ref described a bag face not the parcel; zh no-ref site phrase removed; site mask = whole visible face (it is the side)
- `v2-sa_2084860`（shard0）：U1 site stem and leaves = whole decoration; dropped site so mask (whole decoration anchor) is already correct
- `v2-sa_210703`（round2）：原U1救生圈已有，换独立标签新增任务；U2原白色玻璃顶与源结构相同，已修。
- `v2-sa_2119572`（shard0b）：U2 ref depended on U1 (just to his right)
- `v2-sa_2119572`（shard0b）：U1 only one sleeve visible; target_part made the image-right sleeve
- `v2-sa_2127869`（shard0b）：U4 ref relied on ambiguous white-label bottle wording
- `v2-sa_2127869`（shard0b）：U5 drink is yellow-green not amber; parent zh said red bottle
- `v2-sa_2137778`（round2）：U2 payload made explicit button-front blouse, ensuring structural change from turtleneck.
- `v2-sa_215762`（round2）：U4 existing mask mostly frame; localized support to top-rail center for a direct wreath attachment, excluding door glass and OPEN sign.
- `v2-sa_2176556`（round2）：U1原全景车替换结构不足，改同缆车双层车厢；原悬挂架mask填洞，SAM新车厢mask排除整个不编辑吊架。category同步cable car cabin。
- `v2-sa_218962`（round2）：U1包含另一扶手23像素碎片，已删除。
- `v2-sa_218962`（round2）：U4 replace原仅颜色变化，已改圆钟。
- `v2-sa_2204968`（round2）：U2 white decal on white tube would have low contrast; changed to red.
- `v2-sa_2207729`（shard0）：U4 value matte black ~= current dark lamp colour; changed to white
- `v2-sa_2207729`（shard0）：U3 zh no-ref carried site
- `v2-sa_222823`（round2）：{'unit': 'U4', 'problem': 'Source already has a steel roller shutter, so original replacement mainly changes color.', 'action': 'Replaced payload with hinged double doors and vertical windows.'}
- `v2-sa_225456`（shard0）：U1 zh ref wording mismatch
- `v2-sa_225456`（shard0）：U3 zh no-ref carried elbow site
- `v2-sa_2264516`（round2）：U1 backpack is camouflage, not plain black.
- `v2-sa_2264516`（round2）：U2 jacket to windbreaker was appearance-dominant; revised to sleeveless utility vest.
- `v2-sa_2264516`（round2）：U4 original railing mask filled gaps; SAM3 mask now excludes background.
- `v2-sa_2271073`（shard0b）：U3 upper sleeve did not say which; set image-right
- `v2-sa_2313448`（round2）：U1补明确穹顶灯罩，保证结构替换。
- `v2-sa_2315709`（round2）：U4帽子mask在相邻帽子上有孤立碎点，host交box去掉。
- `v2-sa_2315709`（round2）：U1审查建议的红书不属于目标裤子主人；裤子主人穿唯一的细条纹白衬衫并拿蓝色封面书，改用衬衫花纹定位。
- `v2-sa_2316049`（round2）：U2 was appearance-only replacement; changed to roof-lowered two-seat convertible.
- `v2-sa_2316049`（round2）：U3 also included a bin; exclude it together with bench.
- `v2-sa_2347182`（round2）：U1 original railing mask filled ornamental holes; text and top-rail prompt could not isolate reliable support, retargeted parking sign.
- `v2-sa_2347182`（round2）：U3 two plaques present; specify visible PRINCIPE D’ACAIA text.
- `v2-sa_2367179`（shard0b）：U3 ref between neighboring sacks vague -> anchored on open olive sack
- `v2-sa_2369719`（round2）：U2原白色cabin cruiser不含明确结构变化，已改拖网渔船。
- `v2-sa_2373849`（round2）：U3原梯梁已有红色条，改蓝色检查贴纸使新增独立且自然。
- `v2-sa_2407836`（shard1b）：U4 site windshield corner not visible/segmentable in side view; site changed to door, payload to a logo decal
- `v2-sa_2448967`（shard0b）：U3 ref doubled visible clause; rewritten, site=back
- `v2-sa_2458077`（shard1b）：U3 site rear panel not visible in side view; site changed to painted side panel
- `v2-sa_2497784`（shard1b）：U1 instruction_ref_zh missing 上 (fixed, zh only)
- `v2-sa_2506761`（shard0b）：U3 ref near the front left also fit the far-left brown bottle; anchored
- `v2-sa_2516758`（shard1b）：U3 instruction_ref_zh missing 上 (fixed, zh only)
- `v2-sa_2527153`（shard1b）：U4 site rear rack unsegmentable on tiny partly occluded bicycle; site dropped, payload a small wicker basket, v2 = whole bicycle
- `v2-sa_2539752`（shard1b）：U1 physical_parent metadata named the nearest rider (wrong owner); corrected
- `v2-sa_2553111`（shard1b）：U3 instruction_ref_zh missing 上 (fixed)
- `v2-sa_2564015`（shard1b）：U1 replace_is_attribute (floral blouse -> plain white blouse); payload changed to a short-sleeved T-shirt
- `v2-sa_2599387`（shard1b）：U4 instruction_ref_zh missing 上 (fixed)
- `v2-sa_2618548`（shard1b）：U1 ref foreground stick-holder ambiguous: the boy at right also holds a stick; ref now names the girl on the left
- `v2-sa_2697508`（shard1b）：U2 skirt is coral red not pink; middle woman wears the pale pink long skirt -> ref fixed
- `v2-sa_2697508`（shard1b）：U1 replace shirt->linen shirt was colour-only -> short-sleeved polo
- `v2-sa_2729470`（shard1b）：U1 crossover->compact SUV was recolour-only -> silver pickup truck
- `v2-sa_2729470`（shard1b）：U4 ref beside the nearest bus loose -> left curb beside the nearest red bus
- `v2-sa_2734741`（shard1b）：U2 striped polo -> navy polo was colour-only -> white sleeveless tank top
- `v2-sa_2734741`（shard1b）：U4 payload across the back encoded location -> payload a horizontal white stripe, relation across
- `v2-sa_2748410`（shard1b）：U2 ref beside the white corner building ambiguous among distant dark-coated pedestrians -> distant pedestrian on the right-hand sidewalk
- `v2-sa_2755535`（shard1b）：U2 ref 'silver car behind the yellow car on the left' also fits a farther silver car (x~350-580,y~20-130); ref tightened to top-left corner
- `v2-sa_2765364`（shard0b）：U3 shirt already light blue (no-op attribute) -> mustard yellow
- `v2-sa_2765364`（shard0b）：U4 sleeves of back-facing polo not visible -> retarget to remove blue-white shopping bag
- `v2-sa_2765364`（shard0b）：U5 shirt is pink not neutral pale
- `v2-sa_2775358`（shard1b）：U2 copper pot -> stainless-steel coffee pot was material-only (replace_is_attribute); payload now a white porcelain teapot
- `v2-sa_2775358`（shard1b）：U4 site 'front edge' needed v2 mask: host ∩ box [0,1300,1190,1500]
- `v2-sa_2827573`（shard1b）：U4 lamppost mask contained stray pieces of a separate wall lantern (~x533-560,y300-360); removed in v2 mask
- `v2-sa_2851659`（shard1b）：U3 'foreground flag-bearer' also fits the U1 man in the trench coat; ref now 'left flag-bearer in the navy blazer'
- `v2-sa_2875285`（shard0）：U1 scope_zh 衣领 should be 项圈
- `v2-sa_287810`（shard0b）：U2 man wears navy not black; right-side ambiguous; stray mask blob removed
- `v2-sa_2901296`（shard1b）：U3 ref said 'beside the doorway' but mask [1792,0,1897,186] is the glass balustrade between the right escalator and steel pillar; ref corrected
- `v2-sa_2901296`（shard1b）：old U4 bag was mostly out of frame (y0-63); U4 retargeted to removing the man in light-blue shirt at left [221,0,427,575]
- `v2-sa_2901819`（shard1b）：U1 navy T-shirt -> navy polo was near-invisible; payload now a white polo shirt
- `v2-sa_2938755`（shard0）：U3 zh no-ref would leak site 后背上部; zh fields rewritten
- `v2-sa_2938886`（shard1b）：U2:attribute_value (door already pale blue; 'light blue' -> dark green)
- `v2-sa_2944425`（shard0b）：U2 left-side ambiguous -> image-left
- `v2-sa_2964423`（shard1b）：U1:wrong_color_in_ref (W413 shirt is orange, not yellow)
- `v2-sa_2980326`（shard1b）：U1:ambiguous_ref (three slanted front windshield panels; masked one is image-left)
- `v2-sa_2988008`（shard1b）：U1:replace_is_attribute (blue shirt -> white cotton shirt; now white collarless kurta; 'polo' -> 'shirt')
- `v2-sa_2992365`（shard0）：U5 ref said man holding a bag; he holds a red cup -> brown T-shirt man on top row
- `v2-sa_2992365`（shard0）：U1 charcoal gray ~ current black
- `v2-sa_2992365`（shard0）：U4 long-haired woman ambiguous
- `v2-sa_2992365`（shard0）：U3 zh 短袖 not in English
- `v2-sa_3042396`（shard1b）：U2:ambiguous_ref ('runner on the right' also fits background runners in similar shirts)
- `v2-sa_3126499`（shard1b）：U3 person in pink ambiguous (second man in salmon T-shirt at right); ref now names the red-capped man at the far left and olive-gray bag
- `v2-sa_3165942`（shard1b）：U4 thin blue outline on already blue-glowing letters near-invisible; payload now one small red aviation warning light
- `v2-sa_3171541`（round2）：U1 replacement made explicitly knee-length, belted and double-breasted to ensure structural change.
- `v2-sa_3183045`（round2）：U1 tote to canvas tote was appearance-only replacement; revised to flap-and-buckle satchel.
- `v2-sa_3183045`（round2）：U4 sign ref made more precise via large pale yellow vertical sign.
- `v2-sa_3193863`（shard1b）：U4 ref called the beige jacket a cream vest (fixed)
- `v2-sa_3287892`（shard0b）：U1 left rear wrong (leftmost carrier)
- `v2-sa_3287892`（shard0b）：U2 ref awkward; cap->fez
- `v2-sa_3317825`（shard1b）：U2 pale blue too close to blue gingham jacket (now maroon)
- `v2-sa_3317825`（shard1b）：U3 basket described as white but has an orange rim (ref refined)
- `v2-sa_3317928`（shard1b）：U1 replace floral jar -> plain glass jar was a pattern change only (payload now ceramic bowl)
- `v2-sa_3336366`（shard0）：U2 site side unspecific; made image-left side
- `v2-sa_3376573`（round2）：U1 same-shape sign text replacement made structurally round
- `v2-sa_3389127`（round2）：U1明确只移除可见背部姓名，SAM字母并集排除背带与袖字。U3肩部支持区位于原白标上方。
- `v2-sa_3392242`（shard0）：U1 zh ref described body+handle of a left black suitcase, not matching English
- `v2-sa_3392242`（shard0）：U2 site side unspecific; made image-left side
- `v2-sa_3397098`（round2）：U3两只衣袖都可见，原visible sleeve不唯一，明确画面右侧袖子并选SAM3候选2。
- `v2-sa_3460138`（round2）：{'unit': 'U1', 'problem': 'Generic hiking backpack payload did not ensure structure change.', 'action': 'Specified cylindrical roll-top closure with two external side pouches.'}
- `v2-sa_3460138`（round2）：{'unit': 'U2', 'problem': 'Source jacket mask includes white inner collar, much of ID badge and crossing neckline branch.', 'action': 'SAM purple jacket refined to 14198 pixels; final reviewed before commit.'}
- `v2-sa_3474930`（round2）：{'unit': 'U1', 'problem': 'Classic white motor launch does not ensure clear structural change from existing motorboat.', 'action': 'Specified tall rectangular wheelhouse and large upright windows.'}
- `v2-sa_3474930`（round2）：{'unit': 'U3', 'problem': 'Payload embeds trunk locator and source mask selects entire palm including crown.', 'action': 'Move trunk to placement.site, around relation, self-contained light strand payload; SAM trunk 1701px final viewed before commit. Ref locates palm against high-rise left edge.'}
- `v2-sa_3550286`（round2）：Removed detached background pixels from U1 (7px), U2 (1px); U4 mask narrowed to explicitly named light attachment edge.
- `v2-sa_3562449`（round2）：U4 full railing mask included large gaps/background; anchor tightened to front central top rail.
- `v2-sa_3570130`（round2）：U2 same-class sedan replacement changed to panel van to ensure structural change.
- `v2-sa_3628858`（round2）：{'unit': 'U1', 'category': 'replace_is_attribute', 'evidence': '原蓝箱已平顶木箱，改圆拱铰接盖/搭扣结构。'}
- `v2-sa_3628858`（round2）：{'unit': 'U3', 'category': 'mask_quality', 'evidence': '原与SAM tire均填内孔，依据干净源图内孔轮廓从候选扣675px，4423px最终mask。'}
- `v2-sa_3628858`（round2）：{'unit': 'U4', 'category': 'add_anchor', 'evidence': '船内底被船壁挡住，且船上已有线绳，改同船可见右船首挂一个尚无的圆柱护舷。'}
- `v2-sa_3633416`（shard2）：U1 ref ambiguous: a second tall wooden window further right; added first
- `v2-sa_3635508`（round2）：U1/U5 lower legs are not visible: original masks contain upper trouser fragments only. Retargeted remove to U1 horizontal phone and U5 far-left navy cap, preserving independent owners and interactions.
- `v2-sa_3647055`（shard2）：U4: red-flower planter already on left railing; add duplicated existing item
- `v2-sa_3662681`（shard2）：U1 round->oval sign replace was nearly a no-op; payload changed to chalkboard menu board
- `v2-sa_3689823`（shard2）：U1 replace sedan->blue sedan was a recolour; payload now camper van
- `v2-sa_3712023`（shard2）：U4 dog already wears red vest/neck item; bandana payload replaced
- `v2-sa_3733639`（shard2）：U3 payload perched on top produced awkward double preposition
- `v2-sa_3746390`（shard2）：U4 payload contained site on the lapel, lapel not visible (woman seen from behind)
- `v2-sa_378499`（shard2）：U1: middle window ambiguous -> anchored to car number 22447
- `v2-sa_3792110`（shard2）：U2: several green boxes; ref disambiguated
- `v2-sa_3792110`（shard2）：U3: lettering already gold-tan, colour change not visible -> material change of whole sign
- `v2-sa_3798228`（shard0）：U3 zh ref/no-ref carried site and extra wording; zh fields rewritten
- `v2-sa_3817024`（shard2）：U1: replace payload was a same-category recolour -> hooded sweatshirt
- `v2-sa_3824138`（shard2）：U1: mask missed T-shirt front between vest lapels
- `v2-sa_3824138`（shard2）：U3: payload carried location in the lower corner
- `v2-sa_3868330`（shard2）：U2: nearest-the-noticeboard cue doubtful, reworded
- `v2-sa_3873326`（shard0）：U2 payload referenced the bowl (scene object); rewritten
- `v2-sa_3873326`（shard0）：U1 zh no-ref site phrase removed
- `v2-sa_388235`（shard2）：U1: replace was colour-only (beanie -> beanie)
- `v2-sa_388235`（shard2）：U3: payload carried site on the chest
- `v2-sa_3893247`（shard2）：U2 ref ambiguous with background adult in white headscarf at far left; tightened to foreground adult
- `v2-sa_396678`（shard2）：U4 old mask had two stray blobs on background parasols; replaced by canopy-only v2 mask
- `v2-sa_4003889`（shard2）：U3 shirt is pale gray not white and replacement payload was near-identical; ref colour fixed and payload changed to a dark green hooded sweatshirt
- `v2-sa_4018051`（shard2）：U1 replace payload (plain sage-green cushion) was colour-only; changed to a bolster pillow
- `v2-sa_4023756`（shard2）：U2 replace drawstring bag -> drawstring bag was colour/material only; payload now woven straw tote and ref tightened (second black bag nearby)
- `v2-sa_403217`（shard0）：U3 derived zh no-ref kept site word; explicit blind zh given
- `v2-sa_4063118`（shard2）：U2 ref depended on U1 colour (silver, actually white) and a partly hidden red car sits between; ref rewritten to the dark navy car beyond the white car
- `v2-sa_4132362`（round2）：U1上衣mask含桌边木块孤立碎点，已剔除。
- `v2-sa_4183336`（shard2）：U4 payload contained location phrase (in the lower corner); simplified
- `v2-sa_4202779`（shard0）：U3 2.5.0 mask excluded the basket contents; difficulty/preserve text told evaluators to keep the contents that the edit removes; zh ref duplicated 及提手
- `v2-sa_4203157`（shard2）：U3 mask covered whole canopy while ref said valance; ref rewritten to canopy
- `v2-sa_4203157`（shard2）：U4 payload contained location phrase (in the corner)
- `v2-sa_4228887`（shard2）：U1 replace coat->navy hooded raincoat was a recolour; changed to puffer vest
- `v2-sa_4256768`（shard2）：U3 ref said blue T-shirt but masked shirt is dark grey (blue one belongs to neighbour); ref rewritten
- `v2-sa_4323386`（shard0）：U3 black jacket -> navy blue not clearly visible; changed to light gray
- `v2-sa_4323386`（shard0）：U1 zh ref had extra 中间
- `v2-sa_4351791`（round2）：U1 handlebar already has turquoise bell near x980,y1360; replaced requested new bell with black phone holder.
- `v2-sa_4417376`（shard2）：U4 ref called the silver aluminium pot white; corrected
- `v2-sa_4521545`（shard0）：U1 derived zh no-ref would keep site 安装在顶端; explicit blind zh provided
- `v2-sa_4583482`（shard2）：{'unit': 'U1', 'category': 'attribute_value', 'note': 'statue hat already silvery metal; value changed to glossy black'}
- `v2-sa_4644538`（shard2）：{'unit': 'U2', 'category': 'replace_is_attribute', 'note': 'sign->sign with different text; payload made a round wooden hanging sign'}
- `v2-sa_4660016`（round2）：U1 chest pocket attachment uncertain because chest hidden in side/back view; changed to white shoulder cloth patch with new site mask.
- `v2-sa_4660016`（round2）：U3 plural sleeve request narrowed to the clear visible image-left sleeve.
- `v2-sa_4691001`（round2）：{'unit': 'U1', 'category': 'mask_stray_pixels', 'evidence': 'host的9px分量box[1100,615,1102,621]位于后方人物，已删。'}
- `v2-sa_4691001`（round2）：{'unit': 'U4', 'category': 'invisible_site', 'evidence': '箱提手未显露，handle分割无候选；在同一独立箱体的可见右上角改加贴纸。'}
- `v2-sa_4697965`（shard2）：U3 mask had a stray fragment left of the plank; removed in U3_v2
- `v2-sa_4740557`（shard2）：U3 ref described the bag as long yellow; it is a woven pouch on an orange strap (fixed)
- `v2-sa_4745279`（shard0）：difficulty/preserve called the book fair a record shop (唱片)
- `v2-sa_4745279`（shard0）：U2 middle customer is not short-haired (shoulder-length reddish-blonde)
- `v2-sa_4745279`（shard0）：U5 zh ref 左前方 vs English foreground
- `v2-sa_4745279`（shard0）：U3 zh ref missing 的颜色
- `v2-sa_4767095`（shard0）：U2 ref_zh carried extra （不含铲斗） not in English; zh ref/noref carried the elbow site; zh fields rewritten
- `v2-sa_4791630`（shard2）：U1 replace was colour/text-only poster change (replace_is_attribute); payload rewritten
- `v2-sa_4811077`（shard2）：U4 mask had stray fragments above the rock; cleaned in U4_v2
- `v2-sa_4812017`（shard2）：U1 replace was text-only change of the roof sign (replace_is_attribute); payload rewritten
- `v2-sa_4817785`（shard0）：U2 derived zh no-ref kept site word; explicit blind zh given
- `v2-sa_4880528`（shard2）：U1 pot is dark brown not black and a second orange-flowered shrub exists farther back; ref tightened
- `v2-sa_4933977`（shard2）：U1 strap over blazer also excluded
- `v2-sa_5005559`（round2）：{'unit': 'U1', 'category': 'source_color', 'evidence': '瓶中饮料为橙色且有铝箔封口，ref去除不准确的red。'}
- `v2-sa_5005559`（round2）：{'unit': 'U4', 'category': 'ref_precision', 'evidence': '圆盘花纹可见，食物兼有橙黄颜色；以盘本身描述定位。'}
- `v2-sa_5020470`（shard2）：U1 2.5.0 mask included the black body panel below the seat (y 975-1190)
- `v2-sa_5044363`（shard2）：U2 replace was colour-only (pale pink sleeveless dress -> navy sleeveless dress); payload changed to a jumpsuit
- `v2-sa_5052360`（shard2）：U2 front edge moved to placement.site; v2 mask = front valance strip
- `v2-sa_506936`（shard0）：U2 zh ref 可见紧身裤 did not match English; zh no-ref site phrase removed
- `v2-sa_5074342`（shard2）：U2 car is dark blue, not black (ref fixed)
- `v2-sa_5115384`（shard0）：U3 site top is occupied by the helmet spike; site made explicit (top spike) and zh no-ref made blind
- `v2-sa_5144260`（round2）：{'unit': 'U3', 'category': 'replace_is_attribute', 'evidence': '原payload蓝色方巾仍是颈部布巾，改蓝色领结使形态明确改变。'}
- `v2-sa_5157199`（shard0）：U4 mask stray component at (515,425) removed
- `v2-sa_5157199`（shard0）：U1 derived zh no-ref kept site word; explicit blind zh given
- `v2-sa_5186021`（round2）：{'unit': 'U3', 'category': 'replace_is_attribute', 'evidence': '源上衣已经短袖，原payload短袖亚麻blouse不保证结构变化；明确无袖、尖领、前排纽扣。'}
- `v2-sa_5186021`（round2）：{'unit': 'U3', 'category': 'mask_stray_pixels', 'evidence': '原host10px分量box[1458,1320,1468,1321]位于儿童裤腿，已删。'}
- `v2-sa_5196006`（round2）：{'unit': 'U2', 'category': 'infeasible_site', 'evidence': '衬衫袖口止于上臂，肘部无布料；去除elbow限定，改可见袖子上的椭圆布贴。'}
- `v2-sa_5196006`（round2）：{'unit': 'U1', 'category': 'mask_stray_pixels', 'evidence': '移除围裙box[365,703,385,715]200px与白领巾box[338,516,342,519]10px。'}
- `v2-sa_5199668`（shard0）：U1 site front: noref zh given explicitly without site word
- `v2-sa_5284684`（round2）：{'unit': 'U1', 'category': 'source_color', 'evidence': '干净原图儿童上衣明显青绿色，替代pale描述。'}
- `v2-sa_5322779`（shard2）：U1 payload navy polo vs collared shirt was near colour-only; changed to denim jacket
- `v2-sa_5385604`（shard2）：U2 ref double-with phrasing reworded
- `v2-sa_5390926`（shard2）：U3 rack ref needed nearest (more racks behind)
- `v2-sa_5399663`（shard2）：U1 car is white not silver
- `v2-sa_5399663`（shard2）：U2 replace was effectively text-only; payload made structural
- `v2-sa_5445263`（round2）：{'unit': 'U4', 'category': 'wrong_source_color', 'evidence': '干净原图包与包带为黄色，原green-bag-carrying不符。'}
- `v2-sa_5445263`（round2）：{'unit': 'U2', 'category': 'ref_precision', 'evidence': '目标头面被头发/颈枕遮挡，以人物及搭脚动作唯一指代，避免性别假设。'}
- `v2-sa_5447626`（shard2）：U3 second stool in doorway; ref tightened
- `v2-sa_5508914`（shard2）：U2 parent was called cart; it is a tractor
- `v2-sa_5552382`（shard2）：U2 replace payload was sign->sign text change (replace_is_attribute); changed to a hanging round wall clock
- `v2-sa_5561778`（shard2）：U2 mask had stray islands on red seals beside the door (x380-470,y1000-1180 and x0-62,y760-870); removed in U2_v2
- `v2-sa_5585164`（round2）：U3旧mask散点落在前方男孩袖子上，SAM3新mask排除。
- `v2-sa_5614303`（shard2）：U3 replace tote->beige canvas tote was colour/material only; changed to a wicker picnic basket
- `v2-sa_5636423`（shard2）：U2 replace poster->poster was content-only; changed to a stack of chocolate gift boxes
- `v2-sa_5678708`（round2）：{'unit': 'U5', 'category': 'mask_stray_pixels', 'evidence': '54px分量box[1738,1215,1748,1223]和10px分量box[1754,1116,1762,1118]位于非目标侧袜子，已删。'}
- `v2-sa_5716467`（shard2）：U2 ref facing the camera was ambiguous with the left laptop whose screen faces camera; fixed
- `v2-sa_5735900`（round2）：{'unit': 'U3', 'category': 'mask_stray_pixels', 'evidence': '原host除本袜与鞋面开口脚背外，还含右邻女孩袜子的两个矩形碎片；新site mask全部排除。'}
- `v2-sa_5735900`（round2）：{'unit': 'U5', 'category': 'replace_is_attribute', 'evidence': '源袜已为小腿长袜，原及膝罗纹羊毛袜不保证结构变化，改短踝袜。'}
- `v2-sa_5799580`（round2）：{'unit': 'U3', 'category': 'mask_quality', 'evidence': '原白站牌实际为立体字，host含字间背景及字孔；SAM候选按可见白字像素细化至12102px。'}
- `v2-sa_5799580`（round2）：{'unit': 'U3', 'category': 'replace_is_attribute', 'evidence': '原泛称蓝牌仅保证字/色变化，改椭圆实心牌板保证结构差异。'}
- `v2-sa_5799580`（round2）：{'unit': 'U4', 'category': 'add_anchor', 'evidence': '侧面原已有琥珀反光片；改尚无的顶部太阳能灯，并仅选择前景段黄色顶盖。'}
- `v2-sa_5803931`（shard2）：U1 payload carried site on the handlebars -> moved to placement.site with handlebar v2 mask
- `v2-sa_5827205`（shard2）：U3 replace payload black ribbed beanie was recolour only -> black baseball cap
- `v2-sa_5884999`（shard2b）：U2 ref said blue bucket but masked bucket is white with orange label
- `v2-sa_5919801`（shard2b）：U4 replace was a text-only change (blue sign -> blue EXIT sign); payload now a hanging flat-screen monitor
- `v2-sa_5953627`（round2）：U3源容器已浅圆形，原木碗替换结构变化不足；改带低直边的长方形木托盘，明确轮廓与边壁变化。
- `v2-sa_5969016`（shard2b）：U2 replace dark coat -> beige wool coat was colour/material only; payload now a beige belted trench coat
- `v2-sa_6004886`（shard2b）：U4 ref called the landscape-rectangular sign square
- `v2-sa_6010367`（shard2b）：side pocket not identifiable; site changed to front shoulder strap
- `v2-sa_604524`（shard0）：U4 called an inner top but it is an outer yellow hooded jacket of a different person than the brown jacket
- `v2-sa_604524`（shard0）：U2 zh no-ref carried cuff site
- `v2-sa_604786`（round2）：U3 original mask omitted sunlit lower-left shutter area; new SAM3 mask submitted
- `v2-sa_6065460`（shard0）：U2: chair is occupied by the seated man in the maroon T-shirt, a seat cushion would be hidden; payload changed to a folded blanket draped over it
- `v2-sa_6065460`（shard0）：U4: remove-part sleeves needed part mask (both sleeves, v2)
- `v2-sa_607590`（round2）：U4 material-only replacement made structural with backrest and armrests
- `v2-sa_6082361`（round2）：U4 visible sleeve有两处候选，明确画面右侧长条袖子。
- `v2-sa_6091887`（round2）：U3 included four disconnected fragments on a separate signpost; removed from v2 mask
- `v2-sa_6105776`（round2）：U2 bag hangs from scooter, not cart; structural replacement changed tote to rattan basket.
- `v2-sa_6129691`（round2）：U1 replacement changed sign shape, providing genuine structural change.
- `v2-sa_6208318`（round2）：U2 source is a patterned tunic lower panel over trousers rather than a skirt; rewrote same visible garment part with structural flared pleats.
- `v2-sa_6330783`（round2）：U5 curved wooden handle was only material change; rewritten folding rectangular brass handle for genuine structure change.
- `v2-sa_6347272`（round2）：U2 whole-shirt original mask omitted broad printed torso regions around diagonal strap. Rewrote replacement to both sleeves and segmented sleeves, avoiding ambiguous torso/strap boundary while making real sleeve-length and cuff change.
- `v2-sa_6371955`（round2）：U1 detached bodice speck removed from sleeve v2 mask
- `v2-sa_6391751`（round2）：U2 original chair replacement only changed material and original mask filled backrest openings; rewrote to structural seat replacement and segmented seat.
- `v2-sa_6391751`（round2）：U3 original background-only instruction used whole-board mask including text/logo; narrowed to clearly blank upper-right background.
- `v2-sa_6391751`（round2）：U2 original chair replacement only changed material and original mask filled backrest openings; rewrote to structural seat replacement and segmented seat.
- `v2-sa_6391751`（round2）：U3 original background-only instruction used whole-board mask including text/logo; narrowed to clearly blank upper-right background.
- `v2-sa_6426125`（round2）：U3两侧扶手均可见，明确画面左扶手；原称浅绿椅实际青绿色。U4座缘与短裤紧邻难分，先改指令为同椅清晰左扶手顶面软垫套，保持add与mask交互。
- `v2-sa_6472262`（round2）：U4 left-door locator embedded in payload; moved into placement.site
- `v2-sa_6487910`（round2）：U1木支架处孤立46px非车身碎片，已删。
- `v2-sa_6561145`（round2）：U1 boat-only removal strands driver; changed to contents mode with boat union driver mask.
- `v2-sa_6571872`（round2）：U5原host包含内搭绿色帽兜，SAM重分牛仔外套排除该帽兜。
- `v2-sa_6624578`（round2）：U3原red bag→tan leather handbag结构差异不明确，已改抽绳水桶包。
- `v2-sa_6641776`（round2）：U4原replace仅颜色/材质变化，已改双排扣风衣。
- `v2-sa_6665557`（round2）：U2 original frame ref had a whole-window mask; rewrote to whole-window stained-glass pattern.
- `v2-sa_6714451`（shard0）：U3 and U4 trays both hold squid (U4 called fish tray); refs now use light-blue/dark-blue + squid
- `v2-sa_6714451`（shard0）：U2/U3 Chinese refs said 可见边框 for whole-tray units
- `v2-sa_6714451`（shard0）：U3 site rim was the whole frame; narrowed to the front edge
- `v2-sa_6720037`（round2）：U1/U2/U4原mask覆盖前景栅栏，已按像素细条扣除。
- `v2-sa_6720037`（round2）：U3 replace原仅颜色/文字变化，已改燕尾旗。
- `v2-sa_6724758`（round2）：{'unit': 'U4', 'category': 'payload_site', 'evidence': '原payload含on the chest；移入placement.site并切取上胸部。'}
- `v2-sa_6724758`（round2）：{'unit': 'U4', 'category': 'payload_site', 'evidence': '原payload含on the chest；移入placement.site并切取上胸部。'}
- `v2-sa_6754915`（round2）：{'unit': 'U1', 'category': 'mask_missing_strap', 'evidence': '原mask遗漏包底伸向左侧的蓝色背带；text候选也遗漏，用tracker p2_2并入host。'}
- `v2-sa_6754915`（round2）：{'unit': 'U1', 'category': 'mask_missing_strap', 'evidence': '原mask遗漏包底伸向左侧的蓝色背带；text候选也遗漏，用tracker p2_2并入host。'}
- `v2-sa_6769026`（round2）：U2 rectangular sign to blue sign was appearance-only replacement; revised to round blue OPEN sign.
- `v2-sa_6769026`（round2）：U1 physical_parent_zh incorrectly said left streetlamp.
- `v2-sa_6776348`（round2）：{'unit': 'U1', 'category': 'source_color', 'evidence': '干净原图衬衫偏深紫黑；用深色及纽扣短袖结构替代纯黑描述。'}
- `v2-sa_6776348`（round2）：{'unit': 'U1', 'category': 'source_color', 'evidence': '干净原图衬衫偏深紫黑；用深色及纽扣短袖结构替代纯黑描述。'}
- `v2-sa_6776835`（round2）：U1 removing a grounded main support wheel is implausible; changed operation to replace and specified a wider wheel with a thick knobby tire.
- `v2-sa_6779549`（round2）：U2 whole-window mask did not define recolored surface; changed to four glass panes and tint.
- `v2-sa_6791309`（round2）：U2 mixed frame/panes and already pale yellow frame: segment frame only and recolor cobalt blue.
- `v2-sa_6791309`（round2）：U3 payload now explicitly short-sleeved button-front shirt for structural replacement.
- `v2-sa_6814925`（round2）：{'unit': 'U1', 'category': 'replace_is_attribute', 'evidence': '原tan fleece jacket仍是夹克；改hooded pullover与袋鼠兜形成结构变化。'}
- `v2-sa_6814925`（round2）：{'unit': 'U3', 'category': 'remove_extent', 'evidence': '原chair mask不含椅背搭着的绿外套；指令明确连同外套移除，并提交并集mask。'}
- `v2-sa_6814925`（round2）：{'unit': 'U1', 'category': 'replace_is_attribute', 'evidence': '原tan fleece jacket仍是夹克；改hooded pullover与袋鼠兜形成结构变化。'}
- `v2-sa_6814925`（round2）：{'unit': 'U3', 'category': 'remove_extent', 'evidence': '原chair mask不含椅背搭着的绿外套；指令明确连同外套移除，并提交并集mask。'}
- `v2-sa_682765`（round2）：{'unit': 'U2', 'category': 'mask_stray_pixels', 'evidence': '原mask在左邻白T恤上有2px与1px孤立分量；保留主连通域。'}
- `v2-sa_682765`（round2）：{'unit': 'U2', 'category': 'mask_occluder', 'evidence': '从衬衫mask扣除SAM3识别的胸前墨镜278px。'}
- `v2-sa_682765`（round2）：{'unit': 'U3', 'category': 'source_category', 'evidence': '干净原图可见翻领，改源类别为polo shirt并同步category。'}
- `v2-sa_682765`（round2）：{'unit': 'U4', 'category': 'parent_metadata', 'evidence': '原physical_parent_zh为左路灯，实际目标在最右边缘。'}
- `v2-sa_682765`（round2）：{'unit': 'U2', 'category': 'mask_stray_pixels', 'evidence': '原mask在左邻白T恤上有2px与1px孤立分量；保留主连通域。'}
- `v2-sa_682765`（round2）：{'unit': 'U2', 'category': 'mask_occluder', 'evidence': '从衬衫mask扣除SAM3识别的胸前墨镜278px。'}
- `v2-sa_682765`（round2）：{'unit': 'U3', 'category': 'source_category', 'evidence': '干净原图可见翻领，改源类别为polo shirt并同步category。'}
- `v2-sa_682765`（round2）：{'unit': 'U4', 'category': 'parent_metadata', 'evidence': '原physical_parent_zh为左路灯，实际目标在最右边缘。'}
- `v2-sa_6834065`（round2）：{'unit': 'U3', 'category': 'mask_stray_pixels', 'evidence': '原mask独立195px分量box[57,1350,83,1360]落在人行道，扣除该区。'}
- `v2-sa_6834065`（round2）：{'unit': 'U4', 'category': 'add_count', 'evidence': 'a few数量不明确，改为three。'}
- `v2-sa_6834065`（round2）：{'unit': 'U3', 'category': 'mask_stray_pixels', 'evidence': '原mask独立195px分量box[57,1350,83,1360]落在人行道，扣除该区。'}
- `v2-sa_6834065`（round2）：{'unit': 'U4', 'category': 'add_count', 'evidence': 'a few数量不明确，改为three。'}
- `v2-sa_6841406`（shard3）：U1 ref ambiguous (many streetlamps) and finish matte black ~no-op on dark lamp
- `v2-sa_6841406`（shard3）：U2 ref matched many windows; parent id left_window wrong
- `v2-sa_6841406`（shard3）：U3 flag is blue (state flag) on leftmost pole
- `v2-sa_6841406`（shard3）：U4 two glass shelter roofs, not an entrance canopy; difficulty evidence said middle window
- `v2-sa_6850445`（shard3）：U1 ref: second large basket behind at far left
- `v2-sa_6850445`（shard3）：U3 similar white flags hang inside shop
- `v2-sa_6850445`（shard3）：U4 stool is inside shop, not beside doorway; top already red so red cushion near no-op
- `v2-sa_6859686`（shard3）：U2 replace blue polo -> white polo was a recolor; now sleeveless tank top
- `v2-sa_6859686`（shard3）：U4 payload vague; now traffic cone in pothole
- `v2-sa_6868139`（shard3）：U2 jacket is dark charcoal not brown; deep blue weak under blue light -> bright red
- `v2-sa_6868139`（shard3）：U3 replace with blue COFFEE sign was text/attribute-like -> round hanging wooden sign
- `v2-sa_6868139`（shard3）：difficulty evidence said left Avalon sign
- `v2-sa_68727`（shard3）：U2 ref near the center loose -> woman holding up a phone
- `v2-sa_6895502`（shard3）：U2 trunks already dark (backlit); deep blue near no-op -> bright red
- `v2-sa_6896269`（shard3）：U2 light already matte black -> polished chrome
- `v2-sa_6896269`（shard3）：U3 garment is a red/black patterned salwar outfit, not floral dress
- `v2-sa_6896269`（shard3）：U4 two UNO signs; ref made unique
- `v2-sa_692643`（shard3）：U1 parent id left_plant wrong
- `v2-sa_692643`（shard3）：U2 not a round plant
- `v2-sa_692643`（shard3）：U4 is a background wall lantern beside the flag, not a streetlamp at the right corner; plaque on lantern unnatural
- `v2-sa_6933563`（shard0）：U3 derived zh no-ref kept site word; explicit blind zh given
- `v2-sa_6935352`（shard3）：U1 tram is blue/white not red; ref by number 1102
- `v2-sa_6935352`（shard3）：U4 is a catenary pole number plate, not a station sign
- `v2-sa_6937647`（shard3）：U2 mask had two stray blobs (removed)
- `v2-sa_6943290`（shard3）：U1 hat owner is a hi-vis marshal, not a spectator; hat is a dark bucket hat
- `v2-sa_6943290`（shard3）：U2 orange rain jacket -> navy raincoat was near-recolour; payload changed to grey hooded sweatshirt
- `v2-sa_6977563`（shard3）：U4 back-pocket payload invisible (man faces camera); changed to a plain patch on the jeans
- `v2-sa_7052077`（shard3）：U3 blue canal boat was near-recolour; U4 ref ambiguous among several streetlamps
- `v2-sa_7103552`（shard0）：U3 2.5.0 mask also had a stray fragment on the other sock (~x 461); excluded in v2
- `v2-sa_7103552`（shard0）：U3 zh no-ref carried site
- `v2-sa_7116219`（shard3）：lead spot-check: U3 ref tightened (several children in orange outfits); added owner-relative position and bag colour
- `v2-sa_7125342`（shard3）：U4 sign text misread (Restauration de Bois Dorés)
- `v2-sa_7168629`（shard3）：U1 shirt is light gray not white
- `v2-sa_7168629`（shard3）：U4 photo ambiguous among three stacked printed photos
- `v2-sa_717431`（shard3）：U2 ref central person loose; re-anchored on heart-print jacket
- `v2-sa_7184680`（round2）：U3实际腰头被上衣遮住，改为同裙露出后侧上部添加支持区；at改sewn onto。
- `v2-sa_7184680`（round2）：U3实际腰头被上衣遮住，改为同裙露出后侧上部添加支持区；at改sewn onto。
- `v2-sa_7184680`（round2）：U3实际腰头被上衣遮住，改为同裙露出后侧上部添加支持区；at改sewn onto。
- `v2-sa_718492`（round2）：U1后领口被长发完全遮住，先改指令为同衣露出的上背部，提交该支持区；at改sewn onto。
- `v2-sa_7191982`（shard3）：U1 lamp post already black: matte black finish was a no-op; recoloured dark green
- `v2-sa_7191982`（shard3）：U3 jacket->coat near-recolour; payload changed to puffer vest
- `v2-sa_7205265`（shard3）：U1 black->dark gray barely visible; changed to bright red
- `v2-sa_720948`（shard3）：U4 payload warm yellow glow is a lighting effect; replaced by striped fabric awning over the window
- `v2-sa_7223032`（round2）：U3 sleeve removal changed to whole-top color attribute to avoid ill-posed worn garment removal
- `v2-sa_7229007`（shard3）：U1 value white ~ existing white hubcap -> bright red
- `v2-sa_7229007`（shard3）：U3 ref ambiguous between two wall lanterns, parent_zh said 左墙灯
- `v2-sa_7231402`（shard3）：U1/U2 refs ambiguous (all students in khaki uniforms); re-anchored
- `v2-sa_7231402`（shard3）：U3 potted plant on a sill-less lattice window unnatural; bunting across it
- `v2-sa_7237977`（shard3）：U1 ref on the left ambiguous with second white door; now far left of the yellow building
- `v2-sa_725238`（shard3）：U4 physical_parent_zh said 右下 for a lower-left chair
- `v2-sa_7266192`（shard3）：U4 ref said decoration on the ride but it is a background bow-shaped street light already with blue bulbs; ref and payload rewritten
- `v2-sa_7279175`（shard3）：U3 ref named woman at the right ambiguously; owner is the olive-jacket woman
- `v2-sa_7311948`（shard3）：U3 pattern value yellow and white was a colour, made yellow and white stripes
- `v2-sa_7337463`（shard3）：U1 ref matched three Legacy Gallery signs and payload was mostly recolour; rewritten
- `v2-sa_7337725`（round2）：U4 boot replacement now explicitly ankle-high for structural difference
- `v2-sa_7362739`（shard3）：U3 position wrong (sits just behind cabin, not right side)
- `v2-sa_7365220`（shard3）：U3 several streetlamps on the left
- `v2-sa_7365220`（shard3）：U4 several white doors
- `v2-sa_7374194`（shard3）：U2 tint blue and white was a no-op on a blue/white screen
- `v2-sa_7374523`（shard3）：U2 person behind the performer ambiguous; owner specified
- `v2-sa_7381987`（shard3）：U3 ref also said in the center although the staircase is right of centre; fixed
- `v2-sa_738866`（shard3）：U2 ref near the center vague; replaced by arm-over-railing identifier
- `v2-sa_7407780`（round2）：{'unit': 'U5', 'category': 'mask_quality', 'evidence': '交叉椅腿间原mask夹入草地/后椅像素，SAM候选细化并保留可见左靠背支架；新38983px。'}
- `v2-sa_741247`（shard0）：U5 site front edge below the seats was vague (1800px bench) and front is the far side; respecified as camera-facing side of the left end
- `v2-sa_741247`（shard0）：U3/U5 zh no-ref carried site words; U1 zh ref awkward (短袖的衣袖)
- `v2-sa_7414116`（shard0）：U3 zh ref said 红色 not in English
- `v2-sa_7414116`（shard0）：U4 zh no-ref 位于胯侧 read as a site phrase
- `v2-sa_7420848`（shard3）：U4 ref near the center wrong (cx=0.27); fixed
- `v2-sa_7429655`（shard3）：U4 physical_parent_zh said right-wall railing; it is the balcony railing of the left building; fixed
- `v2-sa_7434362`（round2）：U1 worn sleeve removal replaced by removal of chest badge; retained remove operation
- `v2-sa_7443313`（round2）：U2/U5原替换结构变化不够明确，分别改为粗圆管卷边和波浪扇贝上沿，保留材质与真实结构替换。
- `v2-sa_7464946`（shard3）：U4 ref above the crowd wrong (no crowd) and a second crossing sign exists; U2 payload jacket for hoodie made structural (denim jacket)
- `v2-sa_7470032`（shard3）：U3 small sign ambiguous among several right-side signs; ref now names the green casa hanging sign
- `v2-sa_7470032`（shard3）：U4 window not uniquely referable among many awninged windows -> retargeted
- `v2-sa_7474373`（shard0）：U2 ref (sole facing forward) not unique in the pile; anchored on the striped sandal
- `v2-sa_7493523`（shard3）：U1 mask is the whole background woman; converted to remove of that person instead of re-masking her dress (keeps op mix after U3 became attribute)
- `v2-sa_7493523`（shard3）：lead spot-check: U1 ref ambiguous (a second seated woman with gold headband sits behind the lace-maker); ref now names pearl necklace + left end of the blue table
- `v2-sa_7494564`（shard3）：U4 flag sat on the U3 dome pole (same physical parent); resolved by retarget
- `v2-sa_7494564`（shard3）：U3 ref vague; now green copper dome
- `v2-sa_7506005`（shard3）：U2 payload red jersey ~ recolour of red singlet
- `v2-sa_7506005`（shard3）：U3 removing scooter front wheel under seated rider is absurd; ref ambiguous with rear wheel -> retargeted
- `v2-sa_7522810`（shard3）：U2 person at the right ambiguous with grey-coated man beside him
- `v2-sa_7532719`（shard3）：U4 anchor was a washed-out roofline strip, unsuitable support
- `v2-sa_7542458`（shard3）：U4 ref wording (upper right tower) tightened
- `v2-sa_7543855`（round2）：U5 material/cut rewrite made clearly structural as wide-legged culottes
- `v2-sa_754509`（shard3）：U3 ref vague (across the center)
- `v2-sa_7548763`（shard0）：U1 pale yellow barely differs from the cream shirt -> light blue
- `v2-sa_7548763`（shard0）：U3 preserve/difficulty protected basket contents that the edit removes
- `v2-sa_7548763`（shard0）：U2 zh ref said 摊主 / zh no-ref carried sleeve site
- `v2-sa_7563964`（shard3）：U2 ref ambiguous with other white T-shirts
- `v2-sa_7563964`（shard3）：U4 bag is held (not beside); luggage tag on paper bag unnatural
- `v2-sa_7566194`（round2）：{'unit': 'U2', 'category': 'mask_quality', 'evidence': '握带处原mask与SAM候选均含手指；指定自然的垂直自由端下半段作带扣支持区，mask不含手指。'}
- `v2-sa_7566194`（round2）：{'unit': 'U5', 'category': 'replace_is_attribute', 'evidence': '原及膝牛仔短裤到及膝米色短裤不能保证结构，改及踝工装长裤。'}
- `v2-sa_7567802`（shard3）：U1 bench ref could match occupied bench at far-left edge
- `v2-sa_7628589`（shard3）：difficulty said indoor performance; scene is an outdoor street
- `v2-sa_7639254`（shard3）：U1 vague ref (red SUV and other red vehicle present) fixed
- `v2-sa_7639254`（shard3）：U2 two similar ambulances and replace payload a blue van was near-recolour; now pickup truck
- `v2-sa_7643197`（shard3）：U1 retargeted to the white shirt with shirt v2 mask (also revised text)
- `v2-sa_7643197`（shard3）：U3 ref on the right ambiguous among bent figurines; colour added
- `v2-sa_7643197`（shard3）：U4 two roofs; ref and payload specified
- `v2-sa_7650202`（shard3）：U2 replace wagon->hatchback weak; now delivery van
- `v2-sa_7650355`（shard3）：U3 target was a cylinder cut off at the image edge; retargeted to white box on ground
- `v2-sa_7650355`（shard3）：U4 given site the red door with door v2 mask
- `v2-sa_7677069`（shard3）：U4 several conical hats; ref and payload specified
- `v2-sa_7677069`（shard3）：U3 now includes held sickle so removal leaves no floating tool
- `v2-sa_7685764`（shard3）：U4 several lamp posts; ref anchored to museum and payload specified
- `v2-sa_7698269`（shard3）：U3 mask included a red vehicle edge above the top case; fixed
- `v2-sa_7698269`（shard3）：U1 a second wall lantern exists on the corner building; ref disambiguated
- `v2-sa_7711079`（shard3）：U4 template ref sign at the far right / vague payload rewritten
- `v2-sa_7716977`（shard3）：U1 mask was a coarse blob covering awning/wall, re-segmented to the tall potted plant
- `v2-sa_7716977`（shard3）：U4 sale-sticker payload unnatural on hotel sign
- `v2-sa_77343`（shard3）：U1 material dark wood on an already wooden table was a near no-op
- `v2-sa_77343`（shard3）：U2 mask had a stray fragment at the top edge
- `v2-sa_7735833`（shard3）：U3 wheel is part of the gas-cylinder trolley; removal physically odd -> retargeted to sledgehammer
- `v2-sa_7735833`（shard3）：U1 shirt not cleanly segmentable under smoke; edit moved to the welding helmet
- `v2-sa_7753369`（shard3）：U2 payload loudspeaker ~ megaphone (near no-op replace) -> handheld microphone
- `v2-sa_7753369`（shard3）：U1 ref ambiguous with second raised phone at far right
- `v2-sa_7757919`（shard3）：U1 object is a drone, not an airplane
- `v2-sa_7757919`（shard3）：U4 template ref/payload made specific
- `v2-sa_777091`（shard4）：U2 payload white sedan nearly no-op for white hatchback
- `v2-sa_777091`（shard4）：U4 ref ambiguous among 4 signal heads; payload pedestrian signal on a signal head odd
- `v2-sa_7773451`（shard4）：U1 lamp post already black (no-op) and second lamp post behind
- `v2-sa_7773451`（shard4）：U2 payload near recolour
- `v2-sa_7773451`（shard4）：U4 stone border already exists; second orange/purple flower bed on left
- `v2-sa_7774310`（shard1）：U5 ref did not name the sleeve owner; rewritten
- `v2-sa_7797481`（shard4）：U3 suggested fix (remove whole foreground table) rejected as too large; retargeted to central pennant
- `v2-sa_7797481`（shard4）：U4 second paper notice on left post made ref ambiguous
- `v2-sa_7805976`（shard4）：U4 mask had a 17px stray fragment (removed)
- `v2-sa_7805976`（shard4）：U3 suggested ordinal (second from top) unreliable because top balcony is cut off; used white AC unit instead
- `v2-sa_7810159`（shard4）：U3 ref said upper left but flag is top center; named by colour
- `v2-sa_7813406`（shard0）：U5 physical_parent_zh said gold blouse; corrected
- `v2-sa_7813406`（shard0）：U3 derived zh no-ref kept site word; explicit blind zh given
- `v2-sa_7813406`（shard0）：U5 physical_parent_zh said gold blouse; corrected
- `v2-sa_7813406`（shard0）：U3 derived zh no-ref kept site word; explicit blind zh given
- `v2-sa_7833331`（shard4）：U1 suggested white body panels not used: cab chosen because the blue cage lattice + cargo cannot be masked cleanly; mask includes the cab side window glass
- `v2-sa_7835850`（shard4）：U1 ref lacked colour/number; U4 payload "a route number" vague; removing a power pylon ill-posed
- `v2-sa_7850865`（shard4）：U4 payload "a hanging sign" vague
- `v2-sa_7854521`（shard4）：U3 ref vague (white flag also on right boat)
- `v2-sa_7854521`（shard4）：U4 ref ambiguous (two curved streetlamps), lantern-on-lamp payload odd
- `v2-sa_7892712`（shard4）：U4 ref ambiguous with second banner at top-right corner; payload vague
- `v2-sa_7944519`（shard4）：U1 ref "lower left" ambiguous among several blurry clusters
- `v2-sa_7945941`（shard4）：U3 removing a house door ill-posed
- `v2-sa_7945941`（shard4）：U4 door/sign colours were mis-described (door is pale grey-green, sign is black); plaque on sign unnatural
- `v2-sa_7985091`（shard4）：difficulty evidence referenced the dropped bridge target; updated
- `v2-sa_7991555`（shard4）：U1 car is black not described; U4 sign is black/yellow and a second smaller Kedatangan sign exists
- `v2-sa_8012456`（shard4）：U3 bench was occupied by a seated person (remove ill-posed)
- `v2-sa_8018927`（shard4）：U4 lamp was a tiny lantern cut by the image edge
- `v2-sa_805201`（shard4）：U4 a second yellow caution sign exists near the stairs; U2 payload wooden fence unnatural
- `v2-sa_805201`（shard4）：U3 ref said 'two blue bins' but the bins are white with blue lids (clean source) and a pair is two instances; narrowed to the left bin, re-segmented with SAM3 tracker and re-committed U3_v2; removed non-audit label 'tail_rewrite' from findings_addressed
- `v2-sa_8060797`（shard4）：U1 ref ambiguous with older man white shirt
- `v2-sa_8060797`（shard4）：U2 three identical carved panels
- `v2-sa_8060797`（shard4）：U4 door already has brass fittings
- `v2-sa_8064958`（shard4）：U1 warm beige near no-op on sunlit yellow tower
- `v2-sa_8064958`（shard4）：U3 mask missed green stripe of same flag
- `v2-sa_8066140`（shard4）：U1 two boats; ref made specific
- `v2-sa_8066140`（shard4）：U4 payload generic
- `v2-sa_807381`（shard4）：U2 replace car->sedan same category
- `v2-sa_807381`（shard4）：U4 planter already planted; payload made specific with relation in
- `v2-sa_807381`（shard4）：U4 'middle planter box in the front row' was ambiguous (a smaller fourth box stands at the left of the row); ref now 'the middle one of the three large wooden planter boxes in the front row at the lower right'
- `v2-sa_8092195`（shard4）：U1 railing mask filled (covers people and bicycles behind lattice); lattice-precise mask infeasible so retargeted rather than kept
- `v2-sa_8120561`（shard1）：U3 ZH garbled and red-on-maroon pin low contrast; payload -> white flower pin
- `v2-sa_8139733`（shard1）：U2 ivory white not visibly different on a white rabbit -> matte black; U2 far right foreground also fit cut-off bronze rabbit; U5 ref made specific (gold-eared rabbits also in back rows)
- `v2-sa_8188123`（shard4）：U4 ref: railing is a brown stair handrail; rope fences elsewhere
- `v2-sa_8219544`（shard4）：U1 shirt is navy/white check on clean source so recolour to blue was weak; changed to red
- `v2-sa_8219544`（shard4）：U3 is a teal shop sign board, not a banner
- `v2-sa_8243132`（shard4）：U1/U3 template refs imprecise (car is dark Mini; chalkboard is an A-frame menu)
- `v2-sa_8257697`（shard1）：U1 ZH translated pocket as cloth bag; fixed
- `v2-sa_8290161`（shard4）：U4 payload blue logo on a blue billboard was low-contrast
- `v2-sa_8319146`（shard4）：U2 man is mostly occluded by the U1 man; v2 mask is only the visible coat strip
- `v2-sa_8321304`（shard4）：U1/U2 parents are women (not girls); U3 parent is a young man
- `v2-sa_8336561`（shard4）：U1 mask included the black rail while the edit recolours the felt -> felt-only v2 mask
- `v2-sa_8336561`（shard4）：U4 ref 'shirt at the upper left' was actually a background woman's white sleeve
- `v2-sa_8336561`（shard4）：U3 ref 'card near the lower left' vague among many cards
- `v2-sa_8336561`（shard4）：Correction to sub-agent report: no U3_v2 was committed (none needed: U3 card mask has 0 overlap with U1_v2 and U4); revision JSON is consistent; verified eight of diamonds on the clean source
- `v2-sa_834249`（shard4）：U4 payload 'a hanging sign' vague -> one rectangular blue banner hanging from the lamp
- `v2-sa_83477`（shard5）：U2 ref vague (grey car also present)
- `v2-sa_83477`（shard5）：U4 payload generic
- `v2-sa_8356934`（shard5）：difficulty evidence said 左侧路灯/教堂; corrected
- `v2-sa_8359156`（shard5）：U3 is a brick stack, not a wall
- `v2-sa_8359156`（shard5）：U2 replace payload palm tree made specific (coconut palm)
- `v2-sa_8364417`（shard5）：U1 ref ambiguous with the dark motorbike parked under the tree
- `v2-sa_8364504`（shard5）：U1 turned into target_part edit (white field) with reviewed v2 mask
- `v2-sa_8364627`（shard5）：U2 masked object is a white wooden shutter panel, not a door (audit suggestion called it a narrow door)
- `v2-sa_8364723`（shard5）：U3 ref ambiguous (two blue patio chairs)
- `v2-sa_8364723`（shard5）：U4 ref ambiguous (two hanging baskets) and vague payload
- `v2-sa_8364723`（shard5）：U2 ref loose
- `v2-sa_8382869`（shard5）：U1 blue on white sign with blue lettering -> yellow
- `v2-sa_8382869`（shard5）：U3 chair mask was a fragment heavily occluded by U4 chair; retargeted to hurdle
- `v2-sa_838336`（shard5）：U1 warm beige near-no-op on cream basilica -> pale pink
- `v2-sa_838336`（shard5）：U4 add site hood now has v2 mask
- `v2-sa_8403002`（shard5）：U3: blue lid next to the tub belongs to a different container behind it; not added to mask
- `v2-sa_8405850`（shard5）：U4 mask was a mixture of gas-station canopy and ATM kiosks, rooftop barely visible; retargeted to utility pole
- `v2-sa_8415518`（shard0）：U5 2.5.0 mask included the man black trousers for a top replace; mask_v2 = camouflage jacket only
- `v2-sa_8425235`（shard5）：U4 white arrow payload invisible on white sign that already has a black arrow -> blue tram pictogram
- `v2-sa_8425235`（shard5）：U3 ref loose (second white van right of center)
- `v2-sa_8429220`（shard5）：U1 ambiguous vs small far-left minarets
- `v2-sa_8429220`（shard5）：U3 near the center vague
- `v2-sa_8429220`（shard5）：U4 gate on fence unnatural; other barrier pieces exist
- `v2-sa_8430103`（shard5）：U2 old mask was a cut-off fascia tile chunk, not a sign
- `v2-sa_8472306`（shard0）：U1 site each visible bowl was a multi-part site not segmentable by SAM3 text; narrowed to the topmost bowl
- `v2-sa_8489034`（shard5）：U4 white arrow on white placard not visible -> red arrow
- `v2-sa_8532764`（shard5）：U3 old mask included grass inside wheels and the draped blue jacket
- `v2-sa_8532764`（shard5）：U4 helmet ref ambiguous among several helmets
- `v2-sa_8543461`（shard5）：U1 value red equalled both neighbouring cars; changed to bright yellow
- `v2-sa_8543461`（shard5）：U4 two double-headed lampposts in foreground; ref disambiguated, payload specified
- `v2-sa_8550648`（shard5）：U2 coarse bicycle mask with rack/gravel bleed; tightened with SAM3
- `v2-sa_8550648`（shard5）：U3 mask was only the sign panel (frame/posts left behind on removal); v2 whole freestanding sign
- `v2-sa_8550648`（shard5）：U3 ref 'sign at the lower left' vague
- `v2-sa_8607627`（shard5）：U2 mask excluded the parts filling the bucket; v2 = bucket plus contents
- `v2-sa_8608311`（shard5）：U3 ref ambiguous among several street lamps
- `v2-sa_862087`（shard5）：U4 price board tiny (48x71 px) -> retargeted to blonde woman with pink shopping bag (add black baseball cap)
- `v2-sa_862087`（shard5）：U2 payload made concrete (round porthole window)
- `v2-sa_8631298`（shard5）：U3 'sign at the upper left' generic -> BANK ALJAZIRA sign
- `v2-sa_8631298`（shard5）：U4 payload made concrete
- `v2-sa_8651850`（shard1）：U5 placement relation at not in protocol list -> on
- `v2-sa_8671723`（shard5）：U1 now targets the blue hull (v2 mask hull only) and recolors it bright red
- `v2-sa_8671723`（shard5）：U2 kept as replace with structural payload instead of converting to attribute
- `v2-sa_8671723`（shard5）：U4 railing slice retargeted to lone white mooring post in the water (add seagull)
- `v2-sa_8680793`（shard5）：U3 'plastic bag' is a beige woven sack
- `v2-sa_8680793`（shard5）：U4 payload/ref made concrete
- `v2-sa_8698583`（shard5）：U1 changed to material attribute (white marble) for a bronze statue
- `v2-sa_8698583`（shard5）：U3 facade window retargeted to police officer in front of plinth (remove)
- `v2-sa_8698583`（shard5）：U4 single tiny sneaker retargeted to blonde woman (add red knit beanie)
- `v2-sa_8731521`（shard5）：U3 target was a tiny 79x20 px LED sign; retargeted to man in red polo (U3_v2.png)
- `v2-sa_8731521`（shard5）：U1 colour value blue was a no-op on a blue shirt
- `v2-sa_873326`（shard5）：U3 bag is a dark plastic garbage bag (ref made specific)
- `v2-sa_873326`（shard5）：U4 generic ref/payload made specific
- `v2-sa_8739681`（shard5）：U3 remove of the stanchion would leave both barrier ropes hanging; changed to replace with a marble bollard (operation remove->replace)
- `v2-sa_8739681`（shard5）：build.py apply_unit does not update unit-level "operation" when spec.operation is revised (only instruction_spec.operation changes)
- `v2-sa_876819`（shard5）：U4 anchor was a 35x94 px sign cut off by the image edge; retargeted to the white flag (U4_v2.png)
- `v2-sa_876819`（shard5）：U4 interim flag anchor shared the physical parent with U1 (flag-bearer); retargeted to the male dancer in blue-and-teal at the right (U4_v2.png replaced)
- `v2-sa_8801740`（shard6）：U3 ref umbrella at the upper right ambiguous with purple umbrella further right (fixed)
- `v2-sa_8801740`（shard6）：U4 shirt was an officer khaki uniform shirt; generic badge (fixed)
- `v2-sa_8801740`（shard6）：U1 ref lacked colour (fixed)
- `v2-sa_8802184`（shard6）：U1 target colour blue equalled the current jersey colour (changed to white)
- `v2-sa_8802184`（shard6）：U4 generic red label payload made specific
- `v2-sa_8809691`（shard6）：U1 three lamp posts visible; ref now leftmost
- `v2-sa_8809691`（shard6）：U4 generic bracket payload replaced
- `v2-sa_8813510`（shard6）：U1 several statues; ref and value made precise (golden weakly distinct from existing gold trim)
- `v2-sa_8813510`（shard6）：U3 speakers also on right wall; ref made precise
- `v2-sa_8813510`（shard6）：U4 candle on a column shaft not natural; payload changed to mounted sconce
- `v2-sa_8829935`（shard0）：U2 zh ref described the rim not the tray; zh no-ref site phrase removed
- `v2-sa_8830719`（shard1）：U3 ZH colour red -> orange-red
- `v2-sa_8830987`（shard6）：U1 target colour equalled current shirt colour (now white)
- `v2-sa_8830987`（shard6）：U3 suggested ref (bowl on the scale) was imprecise: the masked bowl is held by the man in the black jacket
- `v2-sa_8830987`（shard6）：U4 generic price tag payload made concrete
- `v2-sa_8855821`（shard6）：U1 ref lacked colour/type (fixed)
- `v2-sa_8861209`（shard1）：U1/U2 Chinese refs did not match English (U2 dangling 其后)
- `v2-sa_8861209`（shard1）：U3 add site visible side meaningless for head-on fender; site removed, anchor mask = fender (no v2 needed)
- `v2-sa_886183`（shard6）：U4: branch at the upper left ambiguous among background branches; vague payload a bird (rewritten)
- `v2-sa_8871336`（shard6）：U4: fence mask included water through railing gaps (refined); ref ambiguous along railing; payload unnatural
- `v2-sa_8874867`（shard6）：U3: banner ref vague (rewritten)
- `v2-sa_8875462`（round2）：Only one U3 sleeve visible; remove extent changed to visible sleeve.
- `v2-sa_8908572`（shard6）：U4: ref overlapped with U3 (both top traffic lights); payload vague (rewritten)
- `v2-sa_8917525`（round2）：U1原来移除穿着足袋；改为独立松放白布，保持remove操作与box交互。U3原裤子host含上衣孤立碎片，新的大腿支持区已排除。
- `v2-sa_892719`（shard0）：U3 zh ref/no-ref carried site phrase 用短带连在瓶嘴旁; aligned
- `v2-sa_892719`（shard0）：U4 zh ref missing 的颜色
- `v2-sa_8934855`（shard1）：U1/U4 add site masks (top/side) committed as host∩box
- `v2-sa_8934855`（shard1）：U5 helmet hangs from standing man hand, not resting on motorcycle; ref fixed
- `v2-sa_8934855`（shard1）：U1/U2 ZH refs had stray 不含面部开口 clause
- `v2-sa_8945299`（shard6）：U1 T-shirt body already navy blue, blue value near no-op -> red
- `v2-sa_8945299`（shard6）：U2 a second thatched roof further left; ref disambiguated
- `v2-sa_8945299`（shard6）：U3 ref named rightmost of three streetlights
- `v2-sa_8952950`（round2）：U1原白衬衫已有胸袋，改为另一侧空白胸前新增星形贴布并提交位置mask。
- `v2-sa_8962292`（shard6）：U2 red scooter has a woman sitting on it -> retargeted to free-standing cream bag
- `v2-sa_8962292`（shard6）：U1 mask included the bucket handle loop -> SAM3 bicycle mask
- `v2-sa_8967676`（shard0）：U1 zh ref wording / missing 的颜色
- `v2-sa_8967676`（shard0）：U2 zh ref/no-ref carried site 套在上段
- `v2-sa_8998938`（shard6）：U3 mask is tall dry grass not bushes
- `v2-sa_8998938`（shard6）：U4 ref railing ambiguous with bridge railings -> white stone balustrade
- `v2-sa_9006288`（shard6）：U1 whole multicoloured occupied rickshaw recolour vague -> folded canopy (v2 mask; a small canopy fragment behind the boy hand not included)
- `v2-sa_9006288`（shard6）：lead spot-check (shard6): U1 canopy mask missed the lilac canopy fragment between the children; recommitted U1_v2 with that fragment included
- `v2-sa_9006757`（shard6）：U2 converted replace->attribute (no natural structural replacement for a train door)
- `v2-sa_9006757`（shard6）：U3/U4 refs ambiguous among repeated lampposts/boxes
- `v2-sa_9013170`（shard6）：U4 generic flower-box payload/relation made concrete
- `v2-sa_9013170`（shard6）：difficulty evidence rewritten
- `v2-sa_9015358`（shard6）：U3 several banners on the hoarding; ref now names the red one right of the trunk
- `v2-sa_9015358`（shard6）：U4 paving tile not uniquely identifiable; retargeted to low stone wall (v2 mask)
- `v2-sa_9015358`（shard6）：difficulty evidence rewritten
- `v2-sa_9033026`（shard6）：difficulty evidence rewritten
- `v2-sa_9033895`（shard6）：U3 door removal ill-posed; now removes the paper notices on the door (v2 mask)
- `v2-sa_9033895`（shard6）：U4 payload made concrete
- `v2-sa_9033895`（shard6）：difficulty evidence rewritten
- `v2-sa_9042900`（shard6）：U1 second white SUV adjacent; ref uses pair ordinal
- `v2-sa_9042900`（shard6）：U4 mask covered both banners of the pair; v2 mask = left banner
- `v2-sa_9042900`（shard6）：difficulty evidence rewritten
- `v2-sa_9066871`（shard6）：case now has no remove unit (U3 remove->attribute per finding)
- `v2-sa_9066871`（shard6）：difficulty evidence rewritten
- `v2-sa_9068084`（shard6）：U1 ref ambiguous among many white-red-white flags
- `v2-sa_9068084`（shard6）：U4 window ref ambiguous among many windows, payload generic
- `v2-sa_9068084`（shard6）：difficulty evidence rewritten
- `v2-sa_9068591`（shard6）：U1 sign already blue (attribute no-op), changed to red
- `v2-sa_9068591`（shard6）：U2 railing mask covered only one section of a continuous railing; retargeted to round road sign (v2 mask)
- `v2-sa_9068591`（shard6）：difficulty evidence rewritten
- `v2-sa_9071097`（shard6）：difficulty evidence rewritten
- `v2-sa_9086959`（shard6）：difficulty evidence rewritten
- `v2-sa_9089846`（shard6）：U3 retargeted to traffic cone (v2 mask) instead of converting to a second attribute, to keep the operation mix
- `v2-sa_9089846`（shard6）：difficulty evidence rewritten
- `v2-sa_9105975`（shard6）：U4 bicycle ref ambiguous (second cyclist at left), payload generic
- `v2-sa_9105975`（shard6）：difficulty evidence rewritten
- `v2-sa_9111693`（shard6）：difficulty evidence rewritten
- `v2-sa_911936`（shard6）：U2 mask refined to T-shirt only via SAM3 (v2) and payload changed to a polo shirt
- `v2-sa_911936`（shard6）：U4 ref said boots (plural) for one boot; retargeted to woman marine front boot (v2 mask)
- `v2-sa_911936`（shard6）：U3 ref rewritten
- `v2-sa_911936`（shard6）：difficulty evidence rewritten
- `v2-sa_9123338`（shard6）：difficulty evidence rewritten (U2 stool is right of centre, not central)
- `v2-sa_9131105`（shard7）：difficulty.evidence_zh mentioned shoes and an upper-left plaque; rewritten
- `v2-sa_9136349`（shard7）：U1 ref the cap at the left ambiguous among crowd caps; value made concrete
- `v2-sa_9136349`（shard7）：difficulty evidence rewritten
- `v2-sa_9142280`（shard7）：difficulty evidence rewritten
- `v2-sa_9161358`（shard7）：U3/U4 refs vague (tail rewrite)
- `v2-sa_9161358`（shard7）：difficulty evidence rewritten
- `v2-sa_9169801`（shard7）：difficulty evidence rewritten
- `v2-sa_9172711`（shard7）：U1 value brown on tan basket weak -> dark red
- `v2-sa_9172711`（shard7）：U3 rock removal near-invisible -> retarget to porter
- `v2-sa_9172711`（shard7）：U4 payload generic
- `v2-sa_9172711`（shard7）：difficulty evidence rewritten
- `v2-sa_9173282`（shard7）：U4 shirt mostly occluded by cabin window frame; retargeted to blue canvas cover
- `v2-sa_9180481`（shard7）：U1 turban is blue, not purple as seen in overlay; U4 payload made specific
- `v2-sa_9187878`（shard7）：U2 ref ambiguous (two windows at left edge); U3 retargeted to tent instead of suggested remove->attribute to keep the remove operation
- `v2-sa_9202366`（shard7）：U1 value blue equalled the current shirt colour -> red
- `v2-sa_9206930`（shard7）：U2 lamp post indistinguishable from 3 adjacent thin lamp posts; retargeted instead of suggested attribute conversion to keep replace
- `v2-sa_921334`（shard7）：U1 boat already white so white was no change; value now bright yellow
- `v2-sa_921334`（shard7）：difficulty evidence rewritten
- `v2-sa_9214653`（shard7）：U3 removed a scooter that a man is riding (ill-posed); retargeted to the pink taxi
- `v2-sa_9214653`（shard7）：U4 ambiguous with a smaller red sign
- `v2-sa_9214653`（shard7）：difficulty evidence rewritten
- `v2-sa_9216210`（shard7）：scene is a hotel atrium not a church; difficulty rewritten
- `v2-sa_9216210`（shard7）：U3 ambiguous between two TUDOR signs
- `v2-sa_9216210`（shard7）：U4 plaque on a ceiling relief unnatural; now a hanging red knot
- `v2-sa_922772`（shard7）：U1 ref vague; now names the boy at the left edge
- `v2-sa_922772`（shard7）：difficulty evidence rewritten
- `v2-sa_9229006`（shard7）：difficulty evidence rewritten (scene is a college building, not a church)
- `v2-sa_9237516`（shard7）：U4 ref vague (bottom-edge gray crate vs wooden crate by hut)
- `v2-sa_9237516`（shard7）：difficulty evidence rewritten
- `v2-sa_9241496`（shard7）：U2 old target was a fragment cut off at the image edge; retargeted to the round blue sign (v2 mask)
- `v2-sa_9241496`（shard7）：difficulty evidence rewritten
- `v2-sa_9247733`（shard7）：U3 old mask was only the upper back of a cut-off blurred chair (lower chair parts overlap a second chair), unsuitable for whole-chair removal
- `v2-sa_9247733`（shard7）：U4 at the left ambiguous with the band on the other wrist
- `v2-sa_9247733`（shard7）：difficulty evidence rewritten
- `v2-sa_9249460`（shard7）：U3 vine fragment had no clear boundary; retargeted to the blue motorbike at the right edge (v2 mask)
- `v2-sa_9249460`（shard7）：difficulty evidence rewritten
- `v2-sa_926201`（shard7）：U3 old mask missed the pannier and saddle of the bicycle; v2 mask covers the whole bicycle
- `v2-sa_926201`（shard7）：U4 payload/relation made concrete (hanging from)
- `v2-sa_926201`（shard7）：difficulty evidence rewritten
- `v2-sa_927124`（shard7）：U1 old mask was only a fragment of a hidden visitor head; retargeted to the gray T-shirt (v2 mask)
- `v2-sa_927124`（shard7）：U2 template ref tightened
- `v2-sa_927124`（shard7）：difficulty evidence rewritten
- `v2-sa_9289265`（shard7）：U2/U3 masks included motorbike mirror/handlebar fragments; v2 masks committed
- `v2-sa_9289265`（shard7）：difficulty evidence rewritten
- `v2-sa_9298533`（shard7）：U1 lamp already black -> dark green
- `v2-sa_9298533`（shard7）：U2 colour-only replace -> wooden notice board
- `v2-sa_9298533`（shard7）：U3 kept remove but on the whole woman (v2 person mask) instead of suggested attribute
- `v2-sa_9298533`（shard7）：difficulty evidence rewritten
- `v2-sa_9327453`（shard7）：U1 ferris-wheel mask filled ~39% sky between spokes and wheel already partly red -> hub emblem recolour (v2)
- `v2-sa_9327453`（shard7）：difficulty evidence rewritten
- `v2-sa_9337303`（shard7）：U2 kept replace (jersey-only v2 mask, sleeveless vest) instead of suggested attribute conversion, for op balance
- `v2-sa_9337303`（shard7）：U3 retargeted to seated spectator instead of the same player boot
- `v2-sa_9337303`（shard7）：difficulty evidence rewritten
- `v2-sa_9357354`（shard7）：U3 speaker mostly occluded by U1 dancer legs -> retargeted to unoccluded equipment box at left
- `v2-sa_9357354`（shard7）：U2 payload changed from suggested red sequined jacket (near-recolour) to a sleeveless fringed vest
- `v2-sa_9357354`（shard7）：difficulty evidence rewritten
- `v2-sa_9359193`（round2）：U3 sleeve site clarified to image-left sleeve, distinct from narrow partly covered opposite sleeve.
- `v2-sa_936576`（round2）：U2原裤子膝下被画面裁断，及膝剪裁位置不可可靠确定；保持remove/point改独立蓝色沙锤，保留全部5单元。
- `v2-sa_9774576`（shard0）：U2 zh no-ref site phrase removed
- `v2-sa_9865645`（round2）：U3浅色泛称改为原图黄色；U5顶部有并排三袋，补最右列。U2明确只移除可准确分割的顶部THE DENIM BROS三词。
- `v2-sa_9898846`（shard0）：U2 contents-mode needed v2 mask (bag+longans)
