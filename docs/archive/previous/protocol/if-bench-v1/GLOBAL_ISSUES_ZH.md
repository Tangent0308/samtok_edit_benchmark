# IF-Bench 全局问题与建议

这些问题针对原协议，不是模型质量结论。证据的上游完整 SHA 和代码行见 [方法核对](METHOD_AUDIT_ZH.md)、[附录方法](APPENDIX_AUDIT_ZH.md)及[来源索引](SOURCE_INDEX.md)。数据证据来自 [release manifest](https://github.com/Tangent0308/samtok_edit_benchmark/blob/6521c8a1daef8a87555c93dea1b156bbab7cbc4b/data/v2_2.6.0/cases.jsonl) 和 [mask contract](https://github.com/Tangent0308/samtok_edit_benchmark/blob/6521c8a1daef8a87555c93dea1b156bbab7cbc4b/samtok_benchmark/v2/instruction_protocol.py)；本机检查 JSON 在实验 `checks/`。

|ID|原协议问题|建议与公平性影响|
|---|---|---|
|G01 必修|将“区域选择器”暗中当成“允许改变的全部像素”。980 个 add mask 是源锚点；全部 3872 个 mask 都声明不是 output-difference GT|保留 selector 语义。原生 hard-mask 方法显式披露 selector-as-edit-mask 适配及原生膨胀；新增物体范围不能从 GT 补入。区域质量差值不能全部解释为读取区域能力|
|G02 必修|mask↔box 写成等价，外轮廓描边宣称等信息|mask→bbox 丢形状，bbox→矩形不恢复原 mask；外轮廓丢洞、遮挡关系和多个组件绑定。记录 lossy conversion；绘制所有外/内边界，允许高保真的独立二值 mask 候选。仍不保证像素等价|
|G03 必修|同 setting 信息等量没有隔离实现约束|按白名单构建公共请求，再交给模型适配器。point 请求不得读取 GT bbox/mask 来放标签或定扩张半径；none 不可读取区域；S3 的 G、hint、refer_object、desc、caption 均不得含私有 ref/category/preserve/completion。Judge 用独立私有侧输入|
|G04 必修|S1 表称所有模型原生支持，与后文 N/A 矛盾|按实际入口与回退路径逐个区分。MICE global-only 已完成最小推理，MaskFlow 有底层 fallback；未验证不自动当作完整方法。把“直接入口不支持”和“模型原则上不会定位”分开|
|G05 必修|MICE/MaskFlow 的 S5 只评有区域单元并列主表|禁止。完成全 K 请求才有完整 UP/JP。缺任何单元整个 case 不完整；已知 unsupported 整 setting N/A；扩展 grounder 行带‡。子集只能以单独名字报告 coverage，不进主表或派生差值|
|G06 必修|point→规划器称不加标记，但混同于确定性转换|内置规划器不需要外部‡，但要记录 planner-active、输入提示、输出区域和调用数；它是学习推断。受控小框与推荐原生流程分别报告。外加规划器才‡，外加分割器†，串联可†‡|
|G07 必修|S2 可以丢弃区域，随后仍计算区域增益/语言依赖|保留区域强制的 paired 行；丢区域只能产生另列 S2-best-adapted 行。否则 G_region 被 dev 选择偏移、Δ_lang 混入适配变化。S4-ref 同理；S5 不能丢掉 no-ref 单元唯一定位输入|
|G08 必修|S2/S3 分别选最佳方案，却把差值解释为语言效应|同一模型同一模态必须共用相同编码策略/预处理/超参，仅变 ref 文本。需分别最优化的性能表另列。规划器是否启用不同也要解释为系统差值而非纯语言因果效应|
|G09 必修|最多4候选、所有候选数相同、strength额外3档、reflection最多3次相互冲突|定义最多4个完整配置，输入方式×strength×坐标格式×PE/PUP/planner开关都计入总数；另报官方推荐流程共用该预算。允许少于4，不重复无效候选凑数；预算是相同上限，不是声称计算量相等。reflection 的内部多候选计 NFE/耗时，不能称一次采样|
|G10 必修|S4/S5 随机分配未规定概率、是否确保混用；S5 又称复现2.6.0|S5 推荐直接沿用 manifest 的 interaction（7种组合，554/553…），不重新抽签；S4-ref/noref 共用确定性表并保证每图≥2种形式，K=2不要求3种齐全。hash种子、表文件、算法一起冻结|
|G11 必修|“dev约10%”没有唯一名单；数据全量已经用于旧实验|按 source/family 隔离，建议108 dev/976 test，已用于本轮 smoke 的图保留在 dev；真实名单等待确认后冻结。披露历史全量结果曾公开，不能宣称新的 split 是从未看过的独立测试集。ref语义终审未完成（manifest中人工验证0/1084）|
|G12 必修|测试前过滤歧义却没排除名单/全局分母规则|先统一审查与冻结 exclusions，所有方法/settings同一名单；不能按模型失败删case。数据编辑须新manifest/hash；若排除则重新报告真实图数/单元数。几何检查不证明指代语义唯一|
|G13 必修|派生 R_mod 分母0未定义；均值式C_mix当因果混合代价|max=0时记N/A并报原值；UP按单元微平均，JP按图平均。C_mix保留为描述性差值；可另报按S4分配的单元匹配基线，JP不能简单按模态边际混合证明因果|
|G14 必修|paired bootstrap 未指定抽样单位，单元相关性被忽略|以源图为cluster，所有模型/settings复用同一图索引；每次重算UP和JP及派生式。固定seed、10000次、95%区间；K桶按图。无同一完整分母时差值N/A|
|G15 必修|GT mask外回贴称“上界”|取消上界说法。GT回贴是 evaluator-oracle postprocessing，可能删除合法新增物体/阴影/替换扩张，也可能提高P；单独诊断，绝不主分数。按用户区域进行回贴也要记录有效范围、融合，不能在point setting读GT做回贴|
|G16 必修|融合分组错误、非融合方法必须再回贴|Flux2KleinInpaint已有latent blend；PowerPaint普通分支计算融合却返回raw，controlnet分支返回paste；BrushNet示例blended=False。取消一刀切回贴。原生流程照官方；额外回贴作为明确命名适配候选，预算内冻结|
|G17 必修|所有模型用同一英文模板与原生token格式冲突|统一语义与单元顺序，不强制字节模板一致。FLUX.3 id/ref token、MICE分隔符、MIRAGE Target 字段必须适配；不得通过模板加入私有对象属性|
|G18 必修|resize回原尺寸掩盖输入预处理差异|保留几何变换链（缩放/pad/crop/对齐），坐标在送入模型的画布中换算。输出先反pad/crop再resize；不能只把变形方图拉回原尺寸。细标记要检查进入VLM后的可见性；模型间分辨率差异完整报告|
|G19 必修|“一次推理”不计区域分支与内部重试，K次的mask坐标随图漂移没规则|按固定unit ID串行；始终在同一源画布坐标链上执行，不隐式跟踪对象；原生融合保留。统计每单元、分支、reflection、planner、rewriter实际调用/NFE、GPU秒。多次更新导致的漂移是方法局限，不能用额外GT修复|
|G20 必修|Judge“看不到输入形式”但旧judge jobs可能继承模式相关文案；标记残留可见|重新构建独立judge输入，只含canonical ref、selector、私有合法效果契约、原图和输出；不含模型名、setting、适配说明。输出中可见残留使完全盲测不可能，称元数据盲测。可视化标记残留人工抽样规则和κ需冻结|
|G21 必修|“学术评测注明许可证即可”|删去自动许可结论。权重门控访问与代码许可证分别核实，Qwen2.1 Research/FLUX.3 Kommunity/Hunyuan地域限制不能省略。许可证条件不明只记录待确认，不能用下载成功替代授权。保留具体条款与未知状态，不代替用户接受条款|
|G22 必修|仓库重命名与旧包/版本混为一体|展示名改IF-Bench；数据release继续2.6.0；评测协议另起ifbench-tiered-v1-rc1；保留旧Python包路径以兼容历史结果。实验新目录，不复用旧jobs/outputs/judge缓存|

执行前建议采用完整修订协议，而不是只修四处接口拼写。两例数据检查只证明所查文件和几何一致，不代替1084张的独立人工语义审核，也不代表已做完dev适配选择。
