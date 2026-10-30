# IF-Bench fairness v2.1：已批准的分辨率与文本完整性修订

用户于2026-10-30批准按复核建议修复、提交推送，并交付新的单机八卡小规模入口。本文件修订下述内容；[v2协议](PROTOCOL.fairness-v2.dev20.md)的信息等量、方法边界、setting、失败、Judge、一次采样及正式执行确认门继续有效。

## 固定变更

| 项目 | v2 | v2.1 | 原因 |
|---|---|---|---|
| Qwen2.1 | pipeline默认`output_resolution=1024` | 作者推荐`output_resolution=2048`，原生保持宽高比 | 区分代码默认与作者推荐，明确采用2K配置 |
| MICE含point的global前导 | 较长标注说明、selector说明和BASE | 一个固定短前导，随后原样保留U/颜色/任务行 | 官方每段实际只保留200个文本条件token；旧S2-point有4/20请求丢失实质任务文字 |
| MICE完整性检查 | 遗漏有效200预算 | 构建包和生成前逐段检查完整chat tokens及原生前200有效token IDs | 不只检查512上限或call.json里的原文 |

MICE短前导固定为：

```text
U marks select source objects, parts, or attachment points. Remove all marks; keep everything else unchanged.
```

只有存在公开point的请求使用此前导；无point请求逐字保留旧形式。原始任务、颜色、U编号、几何、单图选择及global/local绑定不变。官方权重、200-token默认、attention、4步、CFG1均保持。box/mask继续走原生区域接口；point仍是标注图/global文本适配，不冒称原生点控制。

每段使用真实checkpoint tokenizer和原生chat模板（含assistant/thinking标记），要求完整长度≤200，且原生512补齐后的前200有效token与完整序列逐个一致。超限、补齐策略变化或绑定段数不一致，在生成提交前记录明确失败：`attempt_admitted=false`、新调用0、不创建started、不截词、不改写任务、不回退。

Qwen2.1的新请求、参数快照、环境账本与实际pipeline实参均为2048。保留40步、CFG1、KV cache与PE关闭。不在1K/2K分数间择优；显存不足不自动退回1K，失败如实记录。

官方证据：Qwen2.1[推荐尺寸](https://github.com/QwenLM/Qwen-Image-2.1/blob/ab96caa944157ca28a4f36b695c3047549f48f98/README.md#L205-L237)；MICE[200默认及切片](https://github.com/Blowing-Up-Groundhogs/mice/blob/43b289de84dfd184c0ee1b551b0e1bea02f6e92d/flux2/pipeline_flux2_klein.py#L211-L310)。

## 其余方法与范围

Qwen2511、FLUX2、FLUX3、RePlan、MIRAGE保留已核验流程。FLUX3单图最多约4MP、多图每张最多约1MP是[官方原生规则](https://github.com/black-forest-labs/flux-3-image-klein/blob/bfc8889a4497f846416f253a3972a1941ac698b9/src/flux3/pipeline.py#L133-L176)，继续保留。S2−S1包含分辨率/流程变化，不称纯因果区域收益。全部输出仍回源图画布，由同一canonical Judge评分。

沿用v2同一20张dev图、七模型、十setting、seed42。其余88张dev和976张test不动，无新候选搜索。Qwen2.1全200条变化；MICE84条变化（S2-point20、S3-point20、S4-ref15、S4-noref15、S5 14），计划新增284条生成。其余1116条复用精确终态，其中1115张成功图、1条MIRAGE S1原生规划失败，不借修订重试。实际范围须由完整request比较得到。

跨版本configuration digest会改变，不能直接搬旧result。复用须核对父计划、固定代码、完成记录、逐请求原文、公开资产SHA、该模型权重/原生参数及原终态，再绑定新版请求身份；原始调用/trace与历史成本保留，新调用计0。Qwen2.1的1K输出不得用于2K请求。

Judge只按canonical任务/GT、实际输出SHA及配置复用。旧1377个唯一有效评分的raw/repair/历史授权链保留；未变输出对应1093个唯一key。新输出变化则重新评分，不能预先宣称284次新Judge调用。没有新增重采样或通用补评许可。

## 执行与产物

单机8张H100 80GB逐模型分片生成；全部生成终态后统一8卡TP/EP Judge，按模型依次评分。新包位于共享`.ifbench-tmp/fairness-v21-dev20-20261030/`，引用旧包固定环境归档与公开资产；两个包都需保留，旧包不变。

完成dev报告后停止，未授权正式冻结/test。保留每setting七模型对比表、UP/JP及CI、逐请求证据和直接插入的输入/输出图片。正式实验目录不写入本轮材料。旧1K及MICE长前导分数只代表旧配置。

详见[逐模型×setting方法](CURRENT_EVALUATION_ZH.md)、[单机8卡入口](DEV20_RUN_ZH.md)。
