# Inter-Edit：八方法四机全量评测

更新：2026-11-08。实现与冒烟验证完成，正式实验未启动。用户已确认空 mask 处理口径；发布包及校验和以包外交接文件为准。

## 1. 范围与冻结方法

共 6,250 条单轮请求：Local 1,533、Add 1,603、Text Editing 1,084、Texture 389、Remove 1,641。全部保留；输入是原图、公开 mask 与原指令。已发现 6 张官方 mask 全黑，见下面的数据异常处理；不能把它们换成 GT、全图或外部预测 mask。

八方法：SITEdit、Qwen-Image-2.1、Qwen-Image-Edit-2511、RePlan、MIRAGE、FLUX.3 Klein、MICE、FLUX.2 Klein-9B。每请求 seed 42，仅一次采样。SITEdit 固定 `aa5a414`、Pass1 LoRA step 2000、S2 DiT LoRA/CodeInjector adapter 16000、raw SAMTok text encoder、40 步、token guidance γ=2，负向是同一句去掉区域码；不使用 quality-anchor/v5 或 LoRA 强度搜索。

原图统一按冻结 IF-Bench `canvas.py` 转为约 1MP 画布。输出按记录的裁剪/缩放几何回源，保存 raw 和 restored 输出；不使用 GT paste-back。RePlan/MIRAGE 保留原生输出网格及原生规划调用，全部额外调用写入记录。评测用目标图/私有 mask 不进入模型 adapter。

## 2. 模型输入与参数

| 方法 | 公开输入和原生流程 | 固定参数 |
|---|---|---|
| SITEdit | 公开二值 mask 经原生 codec 编码，随后 S2；不调用 Pass1 定位 | 40 步；token guidance 2；raw SAMTok TE |
| Qwen-Image-2.1 | 原图＋二值 mask 两幅图，固定 mask 说明＋原指令 | 40 步；CFG 1；output_resolution=1024；KV cache |
| Qwen-Image-Edit-2511 | 原图＋二值 mask 两幅图，固定 mask 说明＋原指令 | 40 步；true CFG 4；guidance 1 |
| RePlan | 原生规划器读取 mask 内侧红色轮廓标注图＋原指令；原生编辑器使用干净原图 | 40 步；true CFG 4；原生 planner max_new_tokens=2048 |
| MIRAGE | 原生 parser 读取原指令；locator 读取 mask 红色轮廓标注图和确定性提示；编辑器使用干净原图 | 40 步；true CFG 4；patch_ratio=0.4；thinking=false |
| FLUX.3 Klein | 原图和二值 mask 作为两幅原生 reference，使用对应标签；PUP 关闭、boxes=None | distilled；16 步；PUP=false |
| MICE | 原生 instance_masks_yx；一个 global prompt＋一个区域 local prompt | Klein-4B；4 步；guidance 1 |
| FLUX.2 Klein-9B | 原图＋二值 mask 两幅原生输入图，固定说明＋原指令 | distilled；4 步；guidance 1 |

固定配置与权重/代码版本：[配置](../configs/external/interedit_full4.json)。模型只读取 `public.json`；Inter-Edit 的红色轮廓是公开 mask 的确定性表示，保留孔洞，不调用外部定位器。提示词和精确参数见 `external_full/mask_adapters.py`（mask 输入）及冻结 `external_refedit/adapters.py`（纯文字输入）。

## 3. 评分与失败口径

四项已确认原生客观指标：全图 LPIPS（alex）↓、区域内 AlphaCLIP ↑、区域外 AlphaCLIP ↑、Laplacian BSS ↓。固定官方源码 220c1dc，AlphaCLIP ViT-L/14 与已下载 grit1m checkpoint；按源图尺寸和原生 mask 映射执行，CPU FP32。先逐例计分，再汇总全量、编辑类别和语言分组。发布数据缺少 reference_image，因此 S_ref_AlphaCLIP 和 VLM 为 N/A；不把 GT 当参考输入，不调用付费 API。

模型原生失败、前一阶段失败、评分失败和基础设施中断分别记录。报告保留全部应评请求及覆盖率，客观指标报告已取得的真实有效分数；缺分不擅自赋零或“最差值”，不自动重采样。评分/生成记录只写一次；不存在 MagicBrush 的惩罚值规则迁移。原生方法失败会完成该请求的终态记录并继续队列；CUDA/OOM 等基础设施错误停机检查。

## 已确认的数据异常处理

官方 6 张 mask：`00442 / 00454 / 01434 / 02135 / 02185 / 02920`，源文件 RGB 三通道全为 0、alpha 为 255，原始选中像素为 0。不是 alpha 误读，也不是约 1MP 转换造成区域消失。

用户于 2026-11-08 确认：保留全部 6,250 条清单和覆盖率分母，将这 6 条对八种方法一致记录为 `data_input_invalid / N/A`，只对其余 6,244 条推理；不补 mask、不补零，也不把异常记为模型失败。指标均值只由实际获得的有效分数计算，并同时报告 6,250 条应评请求的覆盖率。配置中的 `data_input_errors` 固定这六个 case ID 和处理规则；发布器/入口检查清单完全匹配。公开输入及原始空 mask 字节保持不变。

审计：`/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_full4_20261108/INTEREDIT_FULL_INPUT_AUDIT.json`；6,250 条公开请求和 18,750 份 canonical 资产均已核验。

## 4. 四机调度和提交

一个 ARNOLD 作业 **4 worker × 8 H100 80GB**，均挂载同一 NAS。四台执行完全相同的前台命令：

```bash
bash /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_full4_20261108/start_interedit.sh --attempt run001
```

也可直接用包内 `start.sh --attempt run001`。可选单独预检：四台都使用 `--attempt run001-validate --validate-only`；四台退出释放租约后，以新 attempt 正式运行。三个 benchmark 是三个独立入口/作业，不要让它们同时抢占同一组 32 张卡。

- 节点由 ARNOLD_ID=0…3 自动识别；先验证拓扑，NAS 心跳覆盖环境解包、生成、评分和汇总。
- 按 sequence 平衡分给四节点，再分给每节点八张独立 GPU；连续两轮属于同一 shard。没有跨机模型 TP，也不需要另起 torchrun。
- 每卡按固定模型顺序运行；本节点某模型八卡全部终态后，启动四个 CPU 评分进程，与后续模型生成重叠。CompBench 额外每节点一个 GPT 请求队列。
- 心跳遇到短暂缺失/不完整 JSON 会重试，以最近成功观测到的新序号和本地单调时钟判断失联；不退回旧 OWNER 时间。协调只用 NAS，不占 ARNOLD rendezvous 端口。模型子进程端口为 41000…41007。
- 启动时从 NAS 解包 SHA256 固定的代码和环境到独立 `/tmp/ifbench/external-full4/...`。没有 GitHub 在线下载要求，不依赖本开发机器的 `/opt` 或 `/tmp`。每卡使用前要求空闲显存至少 70,000 MiB；不会结束已有其他进程。
- 只有 node 0 在四节点 EVALUATED 后生成全局报告。汇总逐例记录和真实分母，不平均节点百分比。原始生成/评分记录和 SHA 绑定得到保留。

## 5. 续跑与观察

正常结束或全部自然退出后，四台使用新 `--attempt run002`，结果根不变。完成记录核验输入、配置、源码和输出 SHA 后复用，不重新推理；模型自身失败同样保留。`SIGUSR1` 发给入口 PID 后，当前生成/评分请求结束再退出，四节点会协调停止。

平台强制停止后，先确认四台都已退出；使用 `scripts/external_full_release.py` 和实际原因只释放协调租约。已有受理但没有终态的请求不会自动重判，需保留基础设施证据并明确放行。不要删除 result/admission 来“续跑”。

日志与状态：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_interedit/full4_20261108/cluster/<attempt>/node-{0..3}/`。每卡阶段进度在 `run/attempts/<attempt>-nodeN/*.progress.json`，终态标记为 `gpuG-<model>.terminal.json`；不在每批后重新扫描整个 NAS 结果目录。

## 6. 验证与限制

固定原 pilot 的 03906、05158 两条输入，不按结果选样。八方法共 16 条：15 条生成并完成四项评分；MIRAGE/05158 原生规划抛出 `ValueError: zip() argument 2 is longer than argument 1`，编辑阶段记 blocked_dependency；没有人工改计划或补采样。

| 方法 | 成功出图 / 请求 | 成功请求平均推理秒数（含规划） | 峰值 PyTorch allocated GiB |
|---|---:|---:|---:|
| SITEdit | 2/2 | 53.5 | 38.2 |
| Qwen-Image-2.1 | 2/2 | 60.2 | 19.8 |
| Qwen-Image-Edit-2511 | 2/2 | 128.8 | 57.9 |
| RePlan | 2/2 | 106.3 | 58.0 |
| MIRAGE | 1/2 | 84.4 | 58.1 |
| FLUX.3 Klein | 2/2 | 14.6 | 23.2 |
| MICE | 2/2 | 6.1 | 17.3 |
| FLUX.2 Klein-9B | 2/2 | 6.7 | 34.7 |

这里只验证可运行性，不是全量成绩或候选选择。推理时间不含一次性模型加载；峰值是框架记录的显存，不是整卡占用。原始冒烟记录：`/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_full4_20261108/SMOKE.json`。Inter/Omni 四组原生评分与此前 pilot 输出逐项一致，差值为零：`/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_full4_20261108/METRIC_PARITY.json`。最小样例不能保证所有正式请求都成功。

本分支 27 项 CPU 测试全部通过，包括八方法报告保留非法输入为 N/A 的回归检查。共同检查覆盖四节点×八卡完整分片、连续编辑不读中间 GT、读写心跳竞态、正常/失败 barrier、租约排他、仅终止自有进程、先预检再正式再续跑、所有 mask adapter、非法输入发布阻断。评分环境重新解包后，依赖版本、torch 来源、AlphaCLIP 导入均已验证；无 GPU 或付费调用。

## 7. 路径与代码

| 内容 | 位置 |
|---|---|
| 官方原数据与 SOURCE.json | `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/Inter-Edit-Full-20261108` |
| 全量公开输入及私有评分 manifest | `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/interedit_full4_20261108/bundle` |
| 固定运行包 | `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/interedit_full4_20261108/package-v1` |
| 本轮正式结果根 | `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_interedit/full4_20261108` |
| 最终 JSON/Markdown | 上述根下 `reports/<attempt>/REPORT.{json,md}` |
| 包外交接 | `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_full4_20261108/HANDOFF.md` |
| 临时验证/预检/拼图 | `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_full4_20261108` |

代码：`src/samtok_benchmark/external_full/` 分离数据、adapter、worker、CPU 指标、VLM 判分、报告与协调；`scripts/external_full_entry.py` 实现四机入口；`scripts/arnold/interedit_full4.sh` 是本 benchmark 的独立脚本；`scripts/external_full_publish.py` 在 clean/pushed eval 分支上生成新包和 READY，拒绝覆盖旧包。`configs/external/interedit_full4.json` 为本分支唯一四机配置。冻结 IF-Bench 模块、旧发布包和既有 pilot 正式结果没有修改。

重建输入使用 `scripts/external_full_prepare.py`（Inter/Omni，python -I）或既有 CompBench 全量构造器；下载归档只读取常规图像文件、检查路径和大小，不执行数据包中的代码。所有正式包依赖均在 NAS。
