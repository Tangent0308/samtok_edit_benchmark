# v2.1 dev20 工程故障与修复验证（2026-10-31 更新）

Qwen2.1 的两个固定 GPU 诊断已成功完成；Judge 缓存依赖问题的代码修复与真实证据校验也已通过。**两例通过不等于 177 个失败请求全部补跑，不替换原实验结果。** 原发布包未热更新。诊断、恢复结果和报告仅写入 `/tmp/ifbench/` 或共享 `.ifbench-tmp/`，不写正式 experiments2。

## 已查明的问题

| 问题 | 实际证据 | 已实现的修复 | 当前验证限度 |
|---|---|---|---|
| Qwen2.1 2K 双图请求显存不足 | 200 请求中 23 张出图、177 条失败；177 条都完成 40 次 DiT forward，随后在原生 VAE 解码路径 OOM | CPU 加载后启用官方 `enable_model_cpu_offload(gpu_id=0, device="cuda")`，解码前卸载 DiT 权重 | 两个固定请求均成功；S1 原基线 raw PNG/像素完全相同；S2-point 原 OOM 请求完成，峰值 allocated 43.16 GiB |
| Judge 恢复旧分数时缺文件 | 缓存索引仍引用两份准备机 `/tmp` 收据；第一份在远端报 FileNotFoundError。9 条旧分数已恢复，新增 Judge 调用为 0 | 导出时把 effective 和全部 provenance 原字节复制进新包；启动时先检查索引 SHA、引用路径和全部依赖 SHA | 真实 1,377 条索引、3,703 份文件校验通过；模拟原机器文件不存在也能恢复相同分数 |

本轮生成终态为 1,222 张图、Qwen2.1 的 177 条失败、MIRAGE 的 1 条历史规划失败。新增成功图片为 Qwen2.1 的 23 张与 MICE 的 84 张；其余为精确复用。MICE 本轮新增 84/84 出图成功不等于任务通过。当前唯一输出 key 为 1,200，其中 1,093 可复用旧 Judge，107 尚需新 Judge。

## Qwen2.1 修复的公平性边界

只改变原生组件在 CPU/GPU 间的存放时机，不新增模型、定位器、改写器或额外编辑步骤。清图/标注图顺序、公开 prompt、seed 42、CUDA generator、BF16、40 步、CFG 1、output_resolution 2048、KV cache=True 均保留。不开 VAE tiling/slicing，不降精度、分辨率或步数。

原生声明的卸载顺序是 `text_encoder->transformer->vae`，VAE 的 encode/decode 都有官方 hook。两个实测请求在最终 decoder 入口都记录到 text encoder/DiT 位于 CPU、VAE 位于 CUDA。函数局部 KV cache 仍存活，因此不能外推所有案例必然通过。单个 S1 对照的像素完全一致是已验证事实，不代表对所有请求做了等价性证明。

- [官方 Qwen2.1 声明](https://github.com/huggingface/diffusers/blob/06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a/src/diffusers/pipelines/qwenimage21/pipeline_qwenimage21.py#L183)
- [官方 offload 入口](https://github.com/huggingface/diffusers/blob/06a9cfb86ae8aa69c6a220ba0da0f37b819dde6a/src/diffusers/pipelines/pipeline_utils.py#L1174)
- [完整本机源码复核](/tmp/ifbench/qwen21_memoryfix_20261030/source_review/SOURCE_REVIEW.md)

实现位于 `qwen21_memory.py` 与 `smoke_adapters.Qwen21`。适配器默认仍为 `resident`，保留历史调用；显式选择 `model_cpu_offload` 才启用新路径。修复后的新包准备器会在 `model_specifications.qwen21.execution.memory_policy` 中显式写入该策略，并重新绑定配置及科学身份、固定相关 helper SHA。已发布包保持原样，不会因仓库更新而改变运行配置。

## 等待条件与固定诊断

最初等待条件要求全部 GPU 进程退出；2026-10-31 已确认训练工作流退出后，该条件仍被长期运行的占用程序挡住。用户要求开始修复后，保留旧等待记录（0 调用），使用独立新计划明确登记这一个已观察的后台 GPU PID、GPU UUID 集及每卡不超过 2 GiB 的限制，未停止该程序。仍要求训练工作流退出、所有登记 GPU 至少 70 GiB 可用、主存至少 100 GiB 可用；每 15 秒查询并连续通过 3 次后启动。任何新增 PID、超额显存占用或训练工作流重新出现均阻止启动。诊断时保留后台 GPU 活动，不能用其墙钟时长比较模型速度。

固定诊断只含同一源图的两个请求：

1. `qwen21/S1/v2-sa_607902`：已成功的原生单图对照，比较 raw 图片 SHA 与逐像素差异。
2. `qwen21/S2-point/v2-sa_607902`：已在 VAE 解码 OOM 的双图请求，验证是否能完整出图。

最多两次新编辑调用，不做 Judge、不搜索分数、不替换旧输出。记录真实 forward 次数、GPU 峰值、解码入口各组件设备、最终尺寸和原参数。任一样例失败即结束进程，避免复用异常后的 VAE cache/hook；不自动重试。

计划、代码及原对照文件均绑定 SHA。实际完成记录位于 [PROBE_FINISHED.json](/tmp/ifbench/qwen21_memoryfix_20261030/local_probe_20261031/outputs/PROBE_FINISHED.json)。两例各 40 次真实 DiT forward、1 次 VAE decode，raw 均为 1824×2304；峰值 allocated 分别 35.06/43.16 GiB。S1 raw PNG SHA 与原基线相同，独立逐像素复算最大差为 0。

S2-point 的输出仍可见红蓝圆点残留，未擦除、未换 prompt。两例只证明运行与所述对照事实，不产生新主表分数。[含实际输入、最终 prompt 和输出实图的 Markdown 报告](/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/fairness-v21-repair-report-20261031/REPORT.md)；[独立 GPU 结果复核](/tmp/ifbench/qwen21_memoryfix_20261030/source_review/GPU_DIAGNOSTIC_REVIEW_20261031.md)。

## Judge 修复与旧包恢复的区别

永久修复使用 `portable_judge_entry` 原字节复制 effective/provenance，保留 `origin_path` 作为历史信息；不改原始 JSON 内的历史路径、原始回答、分数或校验规则。`Cache.verify_portable_files` 与启动 preflight 会在生成前发现缺失、篡改或包外依赖。旧记录仍按原有 key/run/output、raw answer 和授权证据核验。

这项更严格的包内引用检查只适用于重新导出的新包。**不能把新 runner 直接热更新到已发布 v2.1 包**：旧索引中还有合法的父共享包引用，已有 9 条 effective 也绑定了原索引 SHA。

两份缺失收据的原字节 payload 已准备。由于远端没有可用的 SSH 认证，本次在本机使用原固定 v2.1 snapshot 和原索引恢复，仅把 `--root` 指向新的共享临时目录；本机原收据仍存在且 SHA 一致。不删除原 ACTIVE/ERROR，不改原 plan/index/READY，也不重新生成图像。

入口 `evaluation/protocol_audit/resume_fairness_v21_judge.py` 外层持原 Judge 的 controller 锁，子 Judge 持新目录锁；先 CPU dry-run、核验 107 个尚未尝试的唯一输出，再等待两例诊断结束和 8 卡显存足够，执行原 Judge 与报告代码。该文件系统跨主机 flock 语义未独立验证；原错误记录已稳定、无原 Judge admission，旧完整入口仍由 ACTIVE 阻止，期间不可另行重启旧入口。

恢复从相同缓存重建 1,093 个旧 key，包括原 9 条；只执行原计划的 107 个新 Judge。原 177 条 Qwen2.1 失败仍进分母，不混入两个诊断结果。恢复结果、完成/错误收据及报告全部写入 [fairness-v21-recovery-20261031/results](/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/fairness-v21-recovery-20261031/results/)，原 root 不会被写成已完成。

详见 [Judge 根因报告](/tmp/ifbench/qwen21_memoryfix_20261030/judge_review/JUDGE_FAILURE_REVIEW.md) 与 [独立修复复核](/tmp/ifbench/qwen21_memoryfix_20261030/judge_review/PATCH_REVIEW.md)。

## 验证与未完成项

- 全量 CPU 测试：268 passed，2 subtests passed；改动 Python 文件 Ruff 检查通过。
- 真实生成运行时 CPU import 通过，明确记录 `cuda_initialized=False`；8 份官方源码 SHA 与固定远端运行时一致。
- 临时迁移的完整 Judge 索引：1,377 条、3,703 份唯一文件全部校验通过；原索引 SHA 未变，新增编辑/评分调用均为 0。
- 实际首个失败 Judge key 在禁止读取所有原路径后，仍能恢复相同 scores/raw_response/有效记录 SHA。
- GPU 两例验证已完成，新增 2 次诊断编辑、0 次诊断 Judge；独立复核的 124 项检查通过。
- 原计划剩余 Judge 和报告由恢复入口继续执行，完成状态以新目录收据为准。没有补跑其余 Qwen2.1 失败请求，没有启动正式冻结/test。
