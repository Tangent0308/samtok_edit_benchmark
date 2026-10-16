# 历史交接 prompt（已完成，不再执行）

以下为 608 已完成 / 196 待修时的原始交接记录。当前 804 个修复任务均已完成，剩余为零；发布入口见 [2.6.0 发布说明](../../docs/RELEASE_2_6_0_ZH.md)。正文中的禁止构建和提交仅适用于当时的逐 case 修复阶段。

```text
继续修复 SAMTok benchmark 的 release 2.6.0，工作是逐个看 case、修 case。协议 2.0 的代码和文档已经改好，no-ref 会在构建时自动生成：不用改协议，也不要手写 no-ref。已完成 608 个 case，还剩 196 个。

仓库：/opt/tiger/tanyue/samtok_edit_benchmark（分支 v2branch），所有命令在仓库根目录运行，Python 用 /opt/tiger/envs/gen/bin/python。
数据根：/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2。

先读：
1. docs/RELEASE_2_6_REPAIR_STATUS_ZH.md：进度和优先级。
2. construction/release_2_6/AGENT_INSTRUCTIONS.md：规则、工具、修订文件格式和逐 case 流程，严格照做。
3. docs/07_SAMTokEdit_Qwen21_指令协议2.0_noref改为盲指代.md 的第 1–5、7、8 节。
4. 范例：construction/release_2_6/revisions/v2-sa_9345888.json 和 v2-sa_2566092.json。

任务：按顺序处理 construction/release_2_6/assignments/round2_all.txt 里的 case。每个 case 的审查问题和需要换的 mask 写在 construction/release_2_6/remaining_work.jsonl，当前状态在 construction/release_2_6/status.json。按状态处理：
- todo：修掉全部审查问题（包括轻微的），把 part_masks_needed 里的单元换成实际被编辑区域的 mask，写修订文件。
- partial：先检查已提交的 U#_v2.png，不对就删掉重做，然后照常修。
- done_unlogged：核对已有修订，补全后写日志。
- done：跳过。

要点：
- 只写三处：修订文件 construction/release_2_6/revisions/<case>.json、数据根下 release_2_6_work/<case>/、日志 construction/release_2_6/logs/round2.jsonl。修订文件的 reviewer 填 round2。
- 不改代码、data/v2_1084/ 和 assets/；不运行不带 --check-only 的 build.py；不做 commit。
- SAM3 分割用 GPU 0（export CUDA_VISIBLE_DEVICES=0）。这张卡与 editMGT 训练共用，不要动其他进程。
- 每个 mask 提交前先看它的 final.jpg。颜色、类别和左右都在干净原图上核实。
- 修不好时依次尝试：改指令 → 修 mask → 在同图换一个独立目标 → 删单元。删单元后每张图仍要至少有 2 个单元、2 种交互形式。
- replace 必须有真实的结构变化：优先改成结构替换，不行再改为 attribute。不给整个人改色，也不把人替换成衣服。
- 不认同的审查问题，在日志里写明证据；日志里的动作如实填写。

看图很占上下文。能派子 agent 的话，每批不超过 10 个 case，同时不超过 3 个，每批回来后抽查 2 个。中断后先运行 construction/release_2_6/status.py，找出还没完成的 case。

完成标准：每个 case 都通过 build.py --check-only --cases <case>，并在日志里写一行。

全部完成后，运行 build.py --check-only --cases $(cat construction/release_2_6/assignments/round2_all.txt) 和 status.py，贴出两者的输出。报告写明：
- 完成的 case 数；
- 单元 keep / revise / retarget / drop 各多少；
- 提交的 v2 mask 数；
- 删除了什么、为什么；
- 被否定的审查问题；
- 未解决的 case；
- 需要人工复核的判断。
```
