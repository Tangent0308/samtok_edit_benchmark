# CompBench：九条请求的授权修复与重测

用户于 2026-11-10 明确授权：修复六条 JSON 语法错误造成的无区域码回退；
对三条原生枚举失败单独调试 prompt；然后重新生成这九条图像。
这是一轮针对已观察失败样例的事后调试，不能描述为未经调试的一次性评测。

旧版 `multitarget_20261110_r2` 的输入、输出和评分全部保留。新代码位于
`external_compbench/recovery9`，不修改旧冻结模块、其他方法或其余请求。

## 修复边界

- 六条格式回退：读取已保存的原始 Pass1 回答，仅修复缺失 `mask_2d` 字段名
  或重复 `label` 字面量这两种无歧义语法错误。修复前后区域码序列必须完全一致；
  标签、顺序、字段和区域码取值仍由方法原有严格解析器校验。不能新编、交换或
  替换区域码，不重新调用这六条的 Pass1。
- 三条枚举：仅使用同一原生 Pass1 模型及原 LoRA、源图和公开指令；greedy，
  512 token。保留每次 prompt、原始回答、耗时及后续逐目标定位回答。先检查结构
  和公开源图上的实例对应关系，再冻结采用的输入；不查看 GT、目标图或编辑得分
  选择 prompt。不调用外部模型。
- S2 维持 aa5a414、原 DiT LoRA/CodeInjector、raw SAMTok TE、40 步、seed 42、
  token guidance 2 和同句去 token 的负分支，每个最终请求一次联合编辑。
- 使用原官方五项客观指标评分。对新九条整体替换，不按新旧分数择优；旧结果和
  所有调试调用继续披露。需要缺失信息时继续保留失败，不能伪造成功。

## 进度

- 已核对：六条均输出了两个完整、编号合法的区域码，原解析器因整段 JSON
  语法错误丢弃所有区域码；三条未形成逐实例枚举。
- 已同步远端工程修订 c9c58d7；远端原实验继续运行。
- 六条格式恢复全部通过原生严格解析，修复前后 12 个区域码逐字相同。
- 对三条请求测试六种原生枚举 prompt：共 18 次枚举、11 次后续逐目标定位；
  全部使用原模型和 LoRA，未调用外部模型、未查看 GT 或编辑得分。
- 冻结共同的 `brief_positions` 提示词，即首个让三条都能返回独立、可解析的
  子指令并完成区域码绑定的版本。兔子、飞机各两个目标。黑鸭返回三个目标，
  公开源图核验发现其包含后方以白色为主的鸭子，语义筛选仍有误选风险。
  该预测保持原样出图和评分，不手工删去目标，不把格式通过写成语义正确。
- 独立控制目录：
  `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/compbench_recovery9_20261110/`。
  `DEBUG_AUDIT.json` 记录所有调试调用，`SELECTION.json` 在 S2 前固定采用的输入。
- 新结果目录：
  `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_compbench/recovery9_20261110/`。
  已于 2026-11-10 07:55 UTC 完成九条重新生成和原官方五项客观评分。
- 结果核验：9/9 出图、9/9 评分，19 个区域码，零无 token 回退；其余 16,416 条
  逐图记录与父报告逐项一致，375 个汇总字段独立重算一致。生成采用代码提交
  `3d3523df880c2f399fd3018468ace165bedd9bb3`，相关 CPU 测试 32 项通过。
- 三条枚举的图像观察：兔子和飞机的目标均已删除；黑鸭图仍误删后方白鸭并漏删
  左侧黑鸭。因此该条恢复了生成和计分，但不能描述为语义修复成功。
- 九条新记录整体纳入独立事后修复表；多目标分组为 144/144 已评分，SITEdit
  五类客观结果共 3,285 条，其他模型与其余请求均未重跑或改动。

## 结果与可视化

- 完整五方法表：新结果目录下 `reports/run001/MERGED_REPORT.md` 与同名 JSON。
- 九条原始评分：`reports/run001/nine/REPORT.json`。
- 独立核验：`reports/run001/VERIFICATION.json`。
- 全部九条对照图：
  `/opt/tiger/tanyue/visualization_tmp/CompBench_Recovery9_20261110/PREVIEWS.md`，
  每条并列源图、Qwen-Image-2.1、修复前 SITEdit、修复后 SITEdit。
- 汇总 JSON SHA256：
  `cc8b1a46eabef1b772d655600c691b23084bfb110a9387a4c11d889bc054f5c5`。

上述结果属于用户授权的事后修复。所有格式错误、未采用的 prompt、额外原生调用
和黑鸭的语义问题均保留，不能将其写成没有额外调试的原始冻结评测。

## 复现入口

`scripts/compbench_recovery9.py` 提供 `prepare`、`worker --stage tokens`、
`worker --stage edit`、`score`、`report` 和 `preview` 子命令。
tokens 阶段仅绑定已保存的原生预测和语法修复证据，不再次调用 Pass1；
编辑阶段消费这些逐目标区域码，一次联合生成。每次调用的完整命令与日志保留在
新控制目录的 `execution/` 下。源文件、输入证据和配置均经 SHA256 绑定，
改变代码或输入后不能复用旧的生成终态。
