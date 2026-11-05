# MagicBrush 进度记录

时间均为 UTC；协议见 [MAGICBRUSH_EVALUATION.md](MAGICBRUSH_EVALUATION.md)。

## 2026-11-05

- 16:24 开始只读核对。系统时间早于 GPU 许可时段；GPU 4–7 约占用 46–50 GB，未启动任何 GPU 进程。
- 已 fetch `v2branch`、`eval-refedit`、`eval-mira`，主 worktree checkout 未改；从 `origin/v2branch` 读取配置／用法。
- 已阅读 RefEdit/MIRA 的 AGENTS、评测与进度文档、公开数据与八方法 adapter、worker、ARNOLD 模板；核对 SITEdit aa5a414 原始主行配置。
- 官方调研确认：test 已公开，535 会话／1,053 轮；HF gated=false；固定 GitHub d2d7f84 与 HF 6c25456；CC BY 4.0。未使用第三方镜像或付费接口。
- 创建独立 worktree `/opt/tiger/tanyue/if-bench-magicbrush` 和 `eval-magicbrush`，基于 `origin/eval-refedit` c9f9447；解除继承的远程分支追踪，防止误推 RefEdit。
- 在实现前写定方案：八方法，两种 mask 输入轨道，独立全轮／连续最终轮；mask-provided 论文区域指标与现行 scorer 整图指标的差异显式披露。

## 当前待办

1. 下载并安全解码 test，核验会话／caption／mask 方向和尺寸；执行重合审计。
2. 实现独立模块、CPU 契约测试、评分和单机 ARNOLD 入口。
3. 19:00 后确认 GPU 4–7 空闲状态，执行每方法 2–3 例端到端 smoke。
4. 用本次实测耗时核算 GPU 小时；遵守本机 8 h 上限，必要时交付入口，正式状态如实记录。
