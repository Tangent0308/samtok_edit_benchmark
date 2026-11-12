# IF-Bench 统一后端开销补测

本实验比较 Qwen-Image-2.1、RePlan、MIRAGE、MICE 和 SITEdit R2@1000。
统一编辑框架、公共依赖、GPU 驻留与计时条件，同时保留方法定义的区域控制。
它是独立的执行变体，不改写已完成的质量评测、原生开销实验或冻结运行包。

## 启动

提交 **1 worker × 8 张 H100 80GB**，共享 NAS 挂载与此前相同。八张卡必须没有其他
计算任务；入口只检查、不结束任何其他进程。前台执行，不加 `nohup` 或 `&`：

```bash
bash /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/ifbench_cost_unified8_20261112/package-v1/start.sh --attempt run001
```

一次入口完成离线环境恢复、配置核验、加载后的数值验证、预热、五方法计时与报告。
先执行 SITEdit，以尽早发现迁移问题；每个方法加载后通过检查和预热再计时。
不需要访问 GitHub、下载权重、连接付费 API，也不使用分布式端口。`/tmp` 至少空闲 50 GiB。

```bash
# 可选：只检查输入、恢复环境及检查 GPU；不执行模型
bash <package>/start.sh --attempt check001 --validate-only
# 可选：每卡每阶段只执行一个固定任务，另写 results/smoke
bash <package>/start.sh --attempt smoke001 --smoke-only
# 中断后续跑；已有终态跳过，不覆盖或重采样
bash <package>/start.sh --attempt run002
```

ADMITTED 无终态时必须先检查中断原因；不能通过换 attempt 自动重新采样。
若显存不足或适配验证失败，停止并保留证据，不自动启用 offload、量化或降低分辨率。

## 共同条件

| 项目 | 固定值 |
|---|---|
| 样本 | 与原生开销实验相同的 20 张图，K=2、3、4、5 各 5 张 |
| Setting | S1、S3-mask；相同公开输入、提示词和各方法已确认的输入表示 |
| 选择 | 公开 case ID 哈希排序，seed 20261112；与质量分数、生成状态无关 |
| 重复 | 每请求 3 次计时，生成 seed 始终 42；600 次编辑，另记规划与预热 |
| 并行 | 每卡一个 worker、batch size 1；相同请求／重复在各方法上使用同一张卡 |
| 软件 | 编辑与基线规划使用同一 Python、Torch 2.8.0、Transformers 5.19.0、Diffusers 0.42.0.dev0、PEFT 0.20.0 |
| 精度 | 主干 BF16；保留训练权重与原生小模块要求的 FP32 精度 |
| 显存 | 每个计时阶段常驻 GPU；关闭 Qwen CPU offload；同一 80GB 预算，报告实际峰值 |
| 加速 | 无新增量化、近似缓存或整模型编译；保留原生精确 KV cache 和方法专用算子 |
| 统计 | 每图取三次中位数，再对图求均值；同时给出共同完成样本的配对表与 K 分桶 |

SITEdit 的 Pass1／mask codec 仍用冻结的原生环境，其 Torch 2.8.0／Transformers 5.19.0
与统一环境一致。它不是图像生成后端。所有**编辑阶段**均在统一 Diffusers 运行环境中执行。

## 各方法保留的机制

| 方法 | 编辑实现 | 保留的采样与区域机制 |
|---|---|---|
| Qwen-Image-2.1 | `UnifiedQwenPipeline` | 原权重、原文本编码器、40 步、CFG 1、原图／标注图输入 |
| SITEdit R2@1000 | 同一个 `UnifiedQwenPipeline` | raw SAMTok TE、全部 DiT LoRA、CodeInjector；40 步；γ=2，负分支为原句去 token；强度 1.0 |
| RePlan | 官方 Diffusers 定制 pipeline | 原规划器、Qwen-2511、区域 FlexAttention、40 步及原 CFG |
| MIRAGE | Diffusers 组件与官方局部／全局循环 | 原规划器、Qwen-2511、40 步、patch ratio 0.4；记录实际区域数 R |
| MICE | 官方 Diffusers 定制 pipeline | Klein-4B、原生区域绑定、4 步、guidance 1 |

Qwen 与 SITEdit 使用相同的分段 SDPA 注意力、最终 RMSNorm 之前的文本特征提取、
Diffusers VAE／Euler 调度流程；二者都直接读语言骨干，避免计算随后丢弃的词表 logits。
SITEdit 保留 CPU seed generator、以画布面积缩放条件图的原生规则；Qwen 保留其 CUDA
generator 和 `output_resolution=1024` 的原生规则。输入输出实际尺寸逐条记录。
两者每请求重置编译状态；此公共 SDPA 路径不编译整模型。

SITEdit S1 一次联合 Pass1，S3-mask 由原生 codec 编码公开 mask；随后一次联合编辑。
S2 中只读取已冻结且核对指纹的码本和注入投影，不加载不参与编辑的 SAM 解码模型。
RePlan、MIRAGE、MICE 的专用注意力／区域循环属于方法本身，不能为追求同一算子而删除。
因此本实验是**统一框架与资源条件**，不声称五方法拥有完全相同的底层算子或 FLOPs。

## 验证与计时边界

发布前 CPU 验证检查：R2 检查点全部 448 个 LoRA 张量名称／形状、码本指纹与
CodeInjector 权重、完整小型 DiT 的首步／缓存路径、40 个请求的条件几何与采样时间表。
随后已在本机第 7 卡对 SITEdit 和 Qwen 分别完成 S1、S3-mask 各一个样例，共四次生成，
完整训练 DiT 数值检查与实际文本特征检查通过。该卡有其他轻量常驻任务，
仅作正确性冒烟，未把耗时作为比较结果。独占远端的八卡计时尚未启动。

每个远端 Qwen／SITEdit worker 在计时前还会检查实际输入的正负文本特征与冻结前端
逐元素一致，以及完整训练 DiT 的首步／缓存路径数值。BF16 DiT 门限预先固定为相对
RMSE ≤0.02 且 cosine ≥0.999；不通过就停止，不根据计时或质量结果放宽门限。
成功预热图片和验证记录保存到各阶段目录，供进一步人工核查输出。

通过这些检查只说明接口、权重和数值路径的实现验证通过，**不证明质量等价**。
后端算子、BF16 舍入和 Euler 数值实现可能改变生成像素。所有新输出保留 RGB 哈希及
与历史图片的对照，不继承原质量分数；质量尚未另行验证时不把新耗时与旧质量绑定成
同一配置的质量—效率结论。

CUDA 同步包围模型调用，计入图像解码、条件构造、文本／VAE 编码与解码及必要传输。
公共资产按原字节预读至 RAM。权重加载、适配验证、PNG／JSON 写盘在计时之外。
`load_seconds` 在本变体中包含加载和初始化数值检查，不当作纯加载性能比较。
阶段模型分开加载；阶段耗时之和不是实测端到端延迟，端到端字段保持 null。

## NAS 产物与监控

结果根：`/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/ifbench_cost_unified8_20261112/results/`。
包外 `handoff.md` 保存完整入口、READY SHA256、源码 commit、plan digest 和核验状态。

| 文件 | 内容 |
|---|---|
| 包内 `READY.json`、`PLAN.json` | 代码／环境／输入绑定、固定配置和样本 |
| 包内 `CPU_VALIDATION.json` | 发布前真实 CPU 数值与检查点核验 |
| 包内 `GPU_SMOKE.json` | 本机两个迁移编辑器的四次真实冒烟，图片在包外 `local-validation/` |
| 包内 `PUBLIC_INPUT_IDENTITY.json` | 相对原生计时包的公开输入字节一致性 |
| `STARTUP.json`、`bootstrap/<attempt>/` | 环境恢复、启动日志、心跳与解释器 |
| `PROGRESS.json` | 当前方法、阶段、八卡状态和当前阶段剩余时间估计 |
| `attempts/<attempt>/<stage>/VALIDATION-*.json` | 远端适配数值检查；失败查看该卡日志 |
| 同目录 `EXECUTION-*.json` | 实际环境版本、显存驻留及专用机制记录 |
| 同目录 `warmup-*.png` | 实际预热输出 |
| `records/` | 逐请求不覆盖的受理、终态、三次计时及第一遍图片 |
| `CAPACITY_LIMIT.json` | 显存不满足统一驻留要求的证据；禁止静默降配 |
| `REPORT.json`、`REPORT.md`、`COST_VS_K.svg` | 五方法总体／配对／K 分桶开销与核查项 |

代码位于 `src/samtok_benchmark/inference_cost/`；新增适配在 `unified.py`。
CPU 验证入口为 `scripts/validate_inference_cost_unified.py`，发布入口为
`scripts/publish_inference_cost_unified.py`。正式 benchmark 的模型适配器、Judge、canvas
和 public 接口保持不变。
