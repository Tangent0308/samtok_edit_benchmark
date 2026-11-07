# 评测与数据文档

## MagicBrush 外部评测（eval-magicbrush）

- [评测方案](MAGICBRUSH_EVALUATION.md)：固定八方法、两种 mask 输入、独立／连续编辑、五项免费指标与重合审计。
- [运行手册](MAGICBRUSH.md)：安全数据入口、CPU 检查、冒烟、四机 32 卡 ARNOLD、恢复与统计。
- [无 mask 全量主结果](MAGICBRUSH_FULL_RESULTS.md)：全部 535 会话、1,053 轮，八方法（含 InstructPix2Pix、HIVE）的独立单轮／连续多轮分数与 95% 区间。
- [完整分析与对比图](MAGICBRUSH_RESULTS.md)：输入方式、失败处理、耗时、实际对比图，以及重合审计和去重合补充结果。
- [经典基线补充](MAGICBRUSH_CLASSIC_BASELINES.md)：InstructPix2Pix／HIVE 原版的固定配置、源码与权重、正式结果。
- [进度记录](MAGICBRUSH_PROGRESS.md)：实际检查、阻塞、偏差及产物位置。

## RefEdit-Bench 外部评测（eval-refedit）

- [评测计划与协议](REFEDIT_EVALUATION.md)：数据、官方 Modified VIEScore、各方法输入、Judge 偏差、统计与重合审计计划。
- [运行手册](REFEDIT.md)：下载、准备、生成、评分与 ARNOLD 入口命令。
- [进度记录](REFEDIT_PROGRESS.md)：实际执行、阻塞与偏差，按时间追加。

## MIRA 外部评测（eval-mira）

- [完整评测文档](MIRA_EVALUATION.md)：每个模型、Judge、两套结果、结果路径、实际图例与 SITEdit 分析。
- [运行手册](MIRA.md)：环境、数据、生成、评分和 CPU 复算命令。
- [实际执行与协议审计](MIRA_FULL_RUN.md)：正式启动、原生调用核验、重合审计记录。
- [RePlan 154 失败与恢复诊断](MIRA_REPLAN_FAILURE.md)：独立测试，不替换正式失败。
- [早期 smoke 记录](MIRA_SMOKE.md)：两例流程验证的历史证据。

## IF-Bench

- [构建流程](CONSTRUCTION.md)
- [评测用法与模型输入](USAGE.md)
- [四机全量运行](FULL_RUN.md)
- [最新结果与分析](RESULTS.md)

当前主评测采用统一约 1MP 公共画布，七个基线及我方 SAMTokEdit、十种 setting。八方法的输入、推理及统一统计口径均见[评测用法](USAGE.md)；SAMTokEdit 的代码和运行记录由独立仓库管理，不加入七基线的冻结运行包。
