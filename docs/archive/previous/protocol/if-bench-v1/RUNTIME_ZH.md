# 本机运行、依赖、权重与最小验证

阶段1仅做连通性验证，未跑dev选择、正式test或Judge。7个主表方法均已生成至少一个输出；这不等于所有setting或完整工作流都已跑通。附录按用户要求推迟到主表完成后再推理。

临时审计根：`/tmp/ifbench/protocol_review_20261027`。8×NVIDIA H100 80GB，部分卡另有任务。下表为单卡进程的PyTorch allocated峰值，**不是最低显存要求**；模型加载、并发争用和不同环境使耗时不可横向作速度排名。MaskFlow未采集峰值，不估算。

|方法/路径|最终结果|输出尺寸|观测allocated峰值|记录|
|---|---|---|---|---|
|qwen2511|generated|1248×832|57.94 GiB|`smoke/qwen2511/result.json`|
|qwen21|generated|1248×832|40.79 GiB|`smoke/qwen21/result.json`|
|flux3|generated|2250×1500|32.79 GiB|`smoke/flux3/result.json`|
|replan|generated|1248×832|57.88 GiB|`smoke/replan/result.json`|
|mirage|generated|1248×832|57.95 GiB|`smoke/mirage/result.json`|
|mice|generated|1248×832|17.33 GiB|`smoke/mice/result.json`|
|mice-s1|generated|1248×832|17.33 GiB|`smoke/mice-s1/result.json`|
|maskflow|generated|1248×832|未采集|`smoke/maskflow/result.json`|

所有生成使用同一张双目标图 `v2-sa_10063996`，seed42。Qwen2511/Qwen2.1是原图+编号框图；FLUX.3是修正后的两个source bbox与no-ref；RePlan关闭planner并注入两个框；MIRAGE直接调用Qwen区域编辑函数、两个框；MICE分别验证双mask和S1 global-only空列表；MaskFlow仅验证U1单mask。标记图只是诊断输入，不是最终冻结renderer。没有按输出质量挑图/改prompt，也没有给这些输出打分。

第二张 `v2-sa_10781767` 仅做源图/mask哈希、point包含与box几何检查，包含remove+add，未运行模型。两张图均列入未来dev，不能留在test。完整1084图的JSON结构/统计已核；全量图像文件未在本轮重新解码检验。

## 未覆盖范围

- RePlan专用TainU规划器与MIRAGE原生Qwen3.5规划器未运行，因此S1、point定位与S5合并的完整流程仍❓；已跑通的是区域编辑内核。MIRAGE最小调用未执行JSONL前处理的10px padding，不能作为完整修订协议的结果。
- MICE的S5 global+regions尚未验证；S1成功不能外推S5。MaskFlow未验证完整K次串行、no-mask回退和add锚点适配。
- Qwen2.1多实例独立mask、所有方法的K=5/最长指令/完整S4和S5，以及可选模型尚未做端到端验证。生成文件存在不能证明绑定正确、无标记残留或编辑质量达标。
- FLUX.2-9B匿名读取配置401，未下载本次可选权重；本地4B不能替代9B。QwenImageEditInpaint所需旧Qwen-Image-Edit完整权重未准备。两项仍为待核，未伪称可运行。

## 环境与失败记录

- Qwen2511、RePlan区域内核、MIRAGE区域内核最终环境 `/tmp/ifbench-audit-clean311`：Python3.11、系统Torch2.8.0+cu128、Transformers5.19.0、Diffusers固定源码 `06a9cfb...`，OMP/torch线程4。RePlan官方固定Transformers4.52.4；这里仅证明编辑内核兼容，不能证明其VLM也兼容5.19。
- Qwen2.1、FLUX.3、MICE成功使用 `/tmp/ifbench-audit-py311`，实际Torch亦为2.8.0+cu128；该环境经历过依赖解析污染，不建议正式复用。此前Qwen2511/RePlan/MIRAGE在CPU→GPU权重搬运阻塞，已保留py-spy栈和超时记录；仅终止本任务自己的三个进程，干净环境重试成功。
- MaskFlow使用Python3.12的 `/tmp/ifbench-audit-runtime`，符合其Python≥3.12要求；显式安装Torch2.8.0+cu128及torchvision0.23，Hydra、PEFT和Poisson依赖见保存的包清单。首次解析得到Torch2.14/cu130，驱动不兼容，纠正后成功。Hydra最终配置保留在`smoke/maskflow/hydra/`。
- FLUX.3 `Models`构造器会提前加载默认未使用的NSFW classifier，本地缺该附属权重导致首次失败。最小验证直接构造官方`Pipeline`后调用官方`generate`，保持上游`safety=False`默认及`pup=False`受控配置；未修改生成算法。首次失败记录保留。
- RePlan官方返回三元组。第一次干净环境推理已完成40步，但审计wrapper误按dict读取返回值，未保存图；修正wrapper后同样输入重跑成功。旧日志`replan_clean311.log`保留，不把这次工具错误算模型不支持。

临时`/tmp`环境不是可长期复现的安装交付。包版本快照在`checks/environment_*.json`；源码由`sources/`与文件hash清单保留。阶段2需在持久环境按方法重建并冻结，不复用有污染的环境，不无限追加隐式依赖。

## 权重来源与许可边界

本机缓存metadata显示Qwen2511、FLUX.3和FLUX.2-4B分别对应SOURCE_INDEX中的当前HF revision。Qwen2.1缓存为`b3179ad355be050328e483a9dfdd9e60cd62adfa`，当前为`d26bb61231c349cf6b7896fa83353113880e1ba3`；逐文件缓存etag与当前Hub blob/LFS哈希比对，27个已缓存文件中仅README和.gitattributes不同，推理权重、配置、tokenizer、processor及LICENSE一致，记录在`checks/qwen21_cached_revision.json`。这是缓存元数据比对，未重新计算数十GB本地权重的内容哈希；正式冻结仍需文件完整性核验。

MaskFlow latest LoRA已从固定HF revision下载到实验weights目录；没有仅靠可变的latest文件名冻结。RePlan规划器Hub公开且metadata可读，但本轮未下载完整权重。其他Hub metadata/HEAD状态见`sources/hub/`。HTTP 401表示该匿名请求无权读取，不表示模型不存在；本轮没有接受任何门控条款。

|模型/代码|已查证的许可/限制|影响|
|---|---|---|
|Qwen2511及旧QwenEdit|model card Apache-2.0|与依赖、数据许可分别记录|
|Qwen2.1|[固定版本Qwen Research License](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/d26bb61231c349cf6b7896fa83353113880e1ba3/LICENSE)|有非商用研究条件，不能概括为Apache|
|FLUX.3|[Kommunity License](https://huggingface.co/black-forest-labs/flux-3-image-klein/blob/337337621b8526e120f2275d250242f4a6bedd75/LICENSE.md)|包含非商用研究及合格用户条件商业使用条款；商业资格涉及关联方合并年收入低于500万美元，不是无条件商业授权|
|FLUX.2-9B / FLUX.1-Fill|各模型非商用权重许可及门控|不要因代码或4B为Apache而套用到9B/Fill|
|MaskFlow / RePlan|各自代码和LoRA/planner模型metadata许可另存|骨干许可独立，不能只记录方法repo许可|
|MICE / TAL|指定tree未找到LICENSE|基础权重许可不自动授权方法代码；标为未确认，不替用户作授权判定|
|Hunyuan|[固定版本许可](https://huggingface.co/tencent/HunyuanImage-3.0-Instruct/blob/2ec2c78bee7d4b94157341fba86c4c2c7b1858b2/LICENSE)|地域定义排除EU、UK、韩国；另有大用户规模条款|
|BrushEdit|[指定源码许可](https://github.com/TencentARC/BrushEdit/blob/0f415c52aa306b5d53f5cb54045fba4fe521fed5/LICENSE)|地域排除EU；与Hunyuan不同|

本表是已读取条款的运行约束记录，不代表替用户接受许可。其余附录依赖、权重与显存未知项见[附录逐方法核对](APPENDIX_AUDIT_ZH.md)，不因本机H100数量足够就声称已验证。

## 静态验证与证据限制

CPU直接执行上游bbox/regex/prompt函数，复现FLUX.3旧schema失败、修正schema可识别、RePlan HTML实体失败/真实尖括号成功、MIRAGE no-ref词法和MICE mask/box互斥断言。结果见`checks/interface_checks.json`。这些不是完整模型推理。

来源采集保留失败记录：GoT和TAL的issue API请求受限，未声称已核阅它们的issue；TAL通过固定SHA的git tree与raw文件补齐源码。其他issue仅最近至多100条，不能证明不存在更早的已知问题。文件行号检查只验证引用在固定源码中存在，论证本身见各方法报告。

8张生成图均可解码、尺寸与记录一致且非单色输出，检查见`checks/image_integrity.json`；展示副本在`/tmp/ifbench/protocol_review_20261027/previews/`。人工仅查看输出完整性，没有评质量分或据此选配置。

目录迁移：按用户要求，本轮所有非正式运行产物已迁至`/tmp/ifbench/protocol_review_20261027/`。迁移校验记录为该目录`relocation_receipt.json`；历史日志/请求/证据清单保留原内容，其中旧绝对路径需按迁移记录映射，不能直接当作当前路径使用。
