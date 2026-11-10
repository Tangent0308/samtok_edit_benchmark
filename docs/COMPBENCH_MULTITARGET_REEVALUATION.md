# CompBench：SITEdit 多目标协议修正与重评

更新：2026-11-10。用户要求按 SITEdit 训练数据协议拆分多目标指令、分别预测区域码后重新评测。本次属于输入协议修正，不做候选提示词搜索或按得分挑选输出。原始运行包、输出、评分、论文表均保留；新分数核验完成前，不将旧多目标行称为已修正结果。

## 方法协议与修正

冻结方法源码为 `sitedit-aa5a414`，继续使用 Pass1 step 2000、S2 adapter 16000、raw SAMTok TE、40 步、token guidance 2、seed 42。源码依据：

- `src/samtok_edit21/pass1/protocol.py:validate_request`：一次请求含 1–5 个有序目标 U1…UK，每个目标返回一个合法 SAMTok mask span。
- `src/samtok_edit21/pass1/grounder.py:Pass1Grounder.ground`：一次贪心生成，同时定位全部目标。
- `src/samtok_edit21/preparation/round2_data.py:multi_edit_prompt`：`Execute all numbered instructions and keep everything else unchanged.`，随后逐行 `U1: …`、`U2: …`。
- `src/samtok_edit21/evaluation/ifbench.py:unit_sentences/pass2_prompt/generate_request`：每个区域码绑定自己的子指令，再执行一次联合 S2 编辑；负分支去掉所有区域码而保留同一组子指令。

先前 CompBench 适配把完整多目标指令当作一个 U1。这会漏掉训练时的逐目标绑定，因此需要重新运行受影响的 Pass1、S2 和五项官方客观评分。

本轮首先覆盖已发布多目标添加、删除的全部 144 个请求；另外只读检查其余客观请求的文本，确认是否存在同类适配问题。拆分只使用原始公开指令，不用目标图、GT mask、目标 caption、对应逆操作或多轮数据补全语义。颜色、服饰、位置修饰语中的 `and` 不作为独立目标。明确的数量词通过等价的逐项表述展开，不擅自补充位置或属性。解析规则与逐条编译产物在新推理前固定，不根据评分修改。

Pass1 对全部子指令执行一次原生联合定位，分别记录 U1…UK 的码。S2 调用方法仓库自己的 `multi_edit_prompt`，逐项放码后一次编辑。继续使用相同 1MP 源画布、回源几何、权重与评分代码；不改基线输入或结果。

## 需要确认的语义边界

以下三条未在文字中给出实例数，而冻结 Pass1 接口要求预先明确 K：`remove the rabbits`、`remove the planes`、`remove all the black ducks except the right one`。用户已于 2026-11-10 明确批准：仅这三条增加一次原生 Pass1 的目标枚举。使用完全相同的 Qwen3-VL-8B-SAMTok＋定位 LoRA，原生图像处理和 greedy 解码，从源画布＋原指令返回逐个目标的删除指令；随后调用原有 `ground` 同时返回各项目标的区域码。枚举最多 512 个新 token、2–5 个目标，左到右、上到下用于稳定顺序；不假设 K=2，不读取评分标注，不换外部模型。枚举提示词、原始回答和额外调用数全部记录；非法回答记录为原生失败，不反复询问或自动修补。该额外提示不是训练协议的原始定位 prompt，是本次获授权的输入适配扩展，报告必须披露。

## 结果与资源

- 旧五方法结果（只读）：`experiments2/SAMTokEdit/external_compbench/full5_20261109/`。
- 新正式输出预定：`experiments2/SAMTokEdit/external_compbench/multitarget_20261110/`。
- 输入审计、计划和调度：`.ifbench-tmp/compbench_multitarget_20261110/`。
- CPU 测试、冒烟及临时日志：`/tmp/ifbench/compbench_multitarget_20261110/`。
- 面向用户的可视化：`/opt/tiger/tanyue/visualization_tmp/CompBench_MultiTarget_20261110/`。

只使用空闲的本机 GPU 4–7，最多四卡；每阶段检查显存和既有进程，不停止任何其他任务。当前八卡均忙，本次尚未启动 GPU。先做 CPU 合同测试、冻结文本拆分，再做少量端到端冒烟并按实测时间估算。正式结果逐条绑定新代码、输入、区域码和输出 SHA；最终对比表中未变行只从原始正式报告读入，修正行只取新评测，不混用两套输入的单条成绩。

## 进度

- 已核对冻结方法的 Pass1 多目标接口、训练 renderer 和 IF-Bench 原生联合推理。
- 已确认当前 `eval-compbench` 与远程一致、工作区干净；旧冻结运行包保持只读。
- 已读取 144 条多目标公开文本，并发现上述三条数量未明的请求。
- 已实现全部 141 条确定性文本拆分与三条原生枚举分支。逐条核对颜色、服饰、共享名词、数量、源参考物及方向关系；没有利用对应逆操作/多轮指令补全目标。
- 原生 Pass1/S2 的调用、回源与官方五项指标复用冻结实现。新模块通过进程内显式注入工厂和 renderer 调用，源码身份加入全部修正文件；旧文件和旧包字节保持不变。
- CPU 回归 33 项通过，覆盖原有完整包合同、逐项绑定、负分支和合并表。144 条真实公开请求已完成只读编译预检；方法配置与冻结 `main_row.json` 逐项一致。
- 待完成：空闲 GPU 上的固定三例冒烟、144 条正式重测、官方评分、汇总和输入/输出对照。

## 运行与恢复

`scripts/compbench_multitarget.py` 包含 `prepare`、`run`、`tokens`、`edit`、`score`、`report` 子命令。新计划冻结原始公开输入、拆分、原始报告 SHA、方法配置和修正源码身份。`run` 先等待空闲 GPU，完成预先固定的三种语法冒烟并估时，再以最多四卡运行全部 144 条；评分只用 CPU。它不会启动多机、访问付费 API 或结束其他任务。

原始记录只读；新的生成、官方评分和合并报告分开存放。合并时强制替换全部 144 条，不能因新分数更低而回选旧输出；未改变的 3,141 条和全部基线复用原始记录，仍报告每方法 3,285 条。`STATUS.json` 记录等待/生成/评分阶段、逐卡完成数和错误。恢复用新 attempt；已有完整记录校验后跳过，已有 admission 但无终态不会自动重跑。固定冒烟结果只用于正确性验证，不混入正式行。

控制目录：`/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/compbench_multitarget_20261110/`。代码提交后归档到其中 `repo/`，后续从快照执行，避免工作区新修改影响已冻结任务。

```bash
/tmp/ifbench/external_bench_20261102/env_v4/bin/python \
  /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/compbench_multitarget_20261110/repo/scripts/compbench_multitarget.py run \
  --control /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/compbench_multitarget_20261110 \
  --attempt run001 \
  --scratch-root /tmp/ifbench/compbench_multitarget_20261110 \
  --gpus 4 5 6 7
```

该命令先检查资源并等待，不会抢占忙卡。不要在已存在 `RUN.lock` 的情况下重复启动。原始 144 条实际合计为 1.019 GPU 小时；这只是旧复合 U1 流程的成本参考。新流程事前暂按四卡空闲后 30–60 分钟安排（含冒烟、加载和评分），等待 GPU 的时间无法由本任务估计；实际预算在固定冒烟结束后写入 `SMOKE_COMPLETED.json`。
