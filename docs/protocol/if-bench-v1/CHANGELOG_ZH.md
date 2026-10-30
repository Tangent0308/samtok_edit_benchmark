# 相对原协议的修订记录

原文件SHA256 `f3dd9a27c4582465d05b47c424eb5b1c96aafee734db271067a2f4790a5d101d`。修订提案ID `ifbench-tiered-v1-rc1`。以下阶段1修改已获用户明确确认；正式test仍须完成dev选型及冻结前确认。逐项上游证据见METHOD_AUDIT_ZH.md、APPENDIX_AUDIT_ZH.md及SETTING_MATRIX_ZH.md。

|原节|原文/规则|修订|为什么 / 公平性影响|
|---|---|---|---|
|开头核对说明|所有细节已经核对|改成分级证据与明确未知项，附完整SHA/源码行/issue|原文存在实际错误，不能用“已核对”替代证据|
|§1|GT mask笼统称区域|明确源selector；add980个为锚点；非输出差分GT|保护原数据任务语义，防止硬范围与目标框偷换|
|§1|只给数据规模|补manifest SHA、K/操作计数、release与协议ID|真正绑定“最新数据”，不混旧资产|
|§2.1 S1|所有模型原生运行|按接口/回退单独说明|单mask CLI无none；MICE存在global-only实测路径|
|§2.1 S4|随机混合、固定seed|补确定性算法、保证≥2种、ref/noref同表、实际计数|K=2不能要求三种齐全；消除分配歧义|
|§2.1 S5|随机混合但称2.6.0完整场景|默认沿用manifest interaction；新随机表另命名|保留已有七组合平衡及可追溯性|
|§2.2|UP/JP沿用，公式未定义边界|写清阈值、分母、global条件、R_mod零分母、缺setting N/A|防止把不完整子集与完整主表比较|
|§2.2|C_mix解释成混合造成的损失|保留描述性差值并限定因果解释|均匀S3均值与实际S4模态权重不同|
|§2.3|评测流程空白|补用户确认→接口→冻结split→dev→freeze→test→Judge→主表→附录|明确阶段门与可复现执行顺序|
|§3 数据|ref唯一性排除未指定时机|统一排除名单，所有方法同一分母，标注人工终审未完成|不能根据模型结果挑样本|
|§3 输入|mask↔box确定性不加标即等量|记录有损与region provenance；禁止恢复隐藏GT|确定性不等于信息保真|
|§3 标记|†/‡只一句定义|内置planner单独标active；外置分割/定位可组合†‡；caption§独立|避免学习推断冒充确定性转换|
|§3 评测|paired bootstrap无抽样单位|按图cluster、10000次、共同索引/95%CI|单图内单元相关，不能当独立样本|
|§3 评测|paste-back上界|改为单独oracle-selector诊断，不进主排名|回贴可能抹掉合法add/阴影，数学上非上界|
|§3 评测|Judge不感知输入形式|限定为元数据盲测，私有视图独立重建|可见残留会暴露适配；旧jobs不能无条件复用|
|§4.1|全模型同一英文模板|统一公共语义，允许原生结构token|FLUX.3/MICE/MIRAGE不能直接吃同一字节格式|
|§4.1|no-ref不改写与MaskFlow替换冲突|只允许已声明的无语义增量词法替换|禁止恢复目标类别/私有ref|
|§4.2|只描外轮廓且等mask信息|含内洞、所有连通域，记录缩放损失|保持部件与遮挡选择信息；仍不声称完全像素等价|
|§4.2|标签放区域外|只能据公开几何放标签；固定颜色/字号/冲突规则|point标签若借隐藏bbox位置会泄漏大小|
|§4.3|由dev决定“原生坐标约定”|真实接口约定按源码；普通文本坐标明确为候选编码|dev不能改变接口事实|
|§4.4|point小框、SAM、grounder无版本|5%小框规则完整记录；SAM/grounder具体revision待附录冻结|不借隐藏GT补范围，预测结果可追溯|
|§4.5 dev|约100张|建议108/976源图隔离；smoke图入dev；披露历史全量暴露|避免本轮试跑case进入test，避免夸大未见测试|
|§4.5 候选|最多4但strength另有3档|最多4完整配置，所有超参和附加组件开关计预算；另报官方推荐流程共用预算|防止隐性倍增搜索预算|
|§4.5 paired|各setting分别选后沿用含糊|S2/S3共用映射；S4/S5组合在候选中定义|差值尽量只改变语言/区域因素|
|§4.5 fallback|S2丢区域计入同一表|主配对必须保留；best-adapted另行|避免dev选择偏差被解释成区域增益|
|§4.5 extras|关闭Qwen PE/FLUX PUP不讲偏离|明确受控消融，官方推荐流程单独补充|不把关闭推荐模块后的成绩当最佳能力|
|§4.5 seed|每case一次但K次/reflection冲突|一次最终输出；unit seed固定派生；内部尝试/NFE计数|计算成本可比较，不偷做best-of-N|
|§4.6|按是否融合统一回贴|保留真实原生融合；外加回贴独立候选|Flux2KleinInpaint已有latent blend；PowerPaint分支返回不同|
|§5|单图/多图分类绝对化|BAGEL支持interleave；HiDream full支持多图；BrushEdit完整与core分行|不人为限制候选或抹掉方法自带能力|
|§6.1|Qwen2511默认40|区分函数50与card40，补CFG1/negative空格/条件分辨率|确保实际CFG和模型推荐匹配|
|§6.2|Qwen2.1独立多色mask假定可用|标❓、加入issue#21；补PE推荐与Research许可|README宣称不等于多实例编码已证|
|§6.3|FLUX2 klein9B guidance4|蒸馏推荐4步/CFG1；源码>1警告忽略|避免把无效配置称作真实CFG4；base另行|
|§6.4|OmniGen2仅引用4/1|区分代码28/4/1与README50步及imageCFG1.2–2|官方推荐范围纳入候选|
|§6.4|Hunyuan至少8×80GB|改为官方推荐；锁full/Distil和2048 token预算|硬件下限未经实测，缩短thinking不是推荐配置|
|§6.5 Step1X|reflection开、thinking关称推荐|函数默认与官方v1p2示例分开，推荐50步两开|不低估原生推理流程|
|§6.5 BAGEL|无多图官方示例|引用维护者issue#83；标记编辑质量仍待测|接受真实支持，不夸大任务效果|
|§6.5 HiDream|编辑必须1参考|只限定特定dev scheduler分支，full多图可选|保持既有高分辨率路线并补合理候选|
|§7.1 FLUX3|id数字/from整数0，动作写desc|字母id/ref_image_0，正文引用与动作，desc静态|实际to_canvas把0变空串，数字id不被完成格式识别|
|§7.1 add|src_bbox填法dev确认|新增row src=null已证；benchmark给锚点，应编码锚点|不能凭空给新增输出GT框|
|§7.2 RePlan|HTML实体标签、未传关键kwargs|真实尖括号、显式expand0/switch.5|官方parser会拒绝实体；方法默认不同于CLI|
|§7.2 point|规划器文本点当已验证原生|受控小框；native-planner单独验证与记录|点文本可传不等于正确定位|
|§7.3 MIRAGE|一份JSONL/错参数名|全局instruction-jsonl+区域crop-instruction-jsonl|按源码schema，否则KeyError/缺全局指令|
|§7.3 MIRAGE|oracle路径默认继承padding10|显式应用并记录padding、latent crop/context变化|直接注入绕过crop脚本，不会自动padding|
|§7.4 MICE|BREAKFLAG泛写、S1 N/A|精确$BREAKFLAG$；S1空mask列表global-only已最小跑通|原S1不支持结论过强；须标退化路径|
|§7.4/7.5 S5|有区域部分报主表|禁止部分U代表完整S5；global/fallback/‡另行验证|固定同任务同分母|
|§7.5 MaskFlow|换成[MASK_AREA]|保留selected region或masked region|官方要求反方向替换|
|§8 Qwen Inpaint|没写基础checkpoint|明确官方示例Qwen-Image-Edit，非自动2511|避免加载错误权重与模型名称偷换|
|§8 BrushNet|blended=True称默认|示例False；True是候选配置|输出融合需真实追踪|
|§8 PowerPaint|只Gradio/必需额外回贴|Controller可封装；普通分支raw、controlnet分支paste|不能只看融合中间变量，也不重复融合|
|§8 InstantX|泛称mask输入/caption|明确control_image/control_mask、30步/CFG4/全图caption推荐|prompt适配要记录内容来源与§|
|§8 BrushEdit|整体S1 N/A|完整VLM流程与BrushNet-core区分|保留真实原生规划能力|
|§8 GoT|直接注入框泛称可用|完整got_input token模板仍待端到端验证|框parser支持不等于任意JSON能跑|
|§8 TAL|第8节一律单maskK次|TAL独立S1任务感知流程，固定骨干/28步/task_type|不把自动定位框架误作mask API|
|§9/10|总览混用默认与待验证方案|逐方法×10列230条结论，runtime另表|显式区分支持、推荐、实测、未知|
|§11 许可证|“学术注明即可”；FLUX3全非商用|列固定版本条款及门控，补Qwen2.1；FLUX3为Kommunity|不替用户自动接受许可，不从用途作无依据法律结论|
|§11 未验证项|四项都推到dev|能由源码/issue解决的本轮解决；仅真实质量/编码未知留dev|减少不必要实验并避免以结果反推接口事实|
|§12 相关工作|无代码/无权重的广泛断言|本轮不重申，视为未审计相关工作清单|任务范围以§10待评方法为主，不能凭旧日期断言今天仍不可用|

本轮报告自身复核还纠正了两处容易误读的代码事实：FLUX2蒸馏guidance>1是warning+ignore而非raise；PowerPaint普通路径计算paste但不返回。最终文档均以真实分支为准，原始日志与源码保留可复查。

用户后续目录要求（2026-10-27）：所有审计、最小样例、dev搜索和调试产物迁到`/tmp/ifbench/`，更新修订协议§10及审计脚本输出根；experiments2仅保留最终冻结后的正式评测产物。这项整理已获明确授权，不属于待确认的评测协议选择。

## 阶段2已确认补充与运行状态（2026-10-27）

|位置|原状态/规则|当前修订|依据与公平性影响|
|---|---|---|---|
|修订稿§6 MIRAGE|要求公开spec.ref，但公共视图没有该字段|有ref且给定区域时，从当前公开instruction确定性提取连续原文目标短语；歧义待核|用户明确选择推荐方案；不读取私有标注，不增加语义信息，S1/S5缺区域保持原生planner|
|执行节点2|逐模型完成即暂停等确认|连续完成所有主表方法，再统一汇报|用户明确更改工作方式；保留dev冻结前确认|
|修订稿§5 split|建议108/976，名单待生成|已生成并经共享输入审核，记录实际split digest|实现状态更新，不改变抽样算法或名单|
|修订稿§6 MICE|完整S5待核|global+regions完整路由已冒烟跑通，质量待dev|不丢弃无区域单元；不是质量通过或候选冻结|
|状态文档|只完成Qwen-2511|全部7主表方法完成冒烟；MaskFlow S1/S5 N/A|从实际JSON汇总，不填未运行质量分数|

环境替换、预处理差异及剩余验证项详见统一冒烟报告；本次没有在test上选方案，也没有因输出不好改seed重跑。原始协议副本保持不变。
